"""Offline GenEval2 evaluation-to-retry planner for manual file transfer.

This module keeps the cross-machine contract JSON-only. Machine A generates an
image package. Machine B reads that package, obtains or normalizes GenEval2
feedback, updates candidate-level memory, optionally calls a teacher, and emits
a retry action package that can be manually copied back to Machine A.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from gen_retry.evaluators.geneval2_adapter import Geneval2Adapter
from gen_retry.evaluators.geneval2_result_normalizer import (
    load_geneval2_score_rows,
    normalize_geneval2_score_list,
)
from gen_retry.schemas.actions import ActionValidationError, RetryReplanAction
from gen_retry.schemas.reports import NormalizedConstraint, NormalizedEvalReport
from gen_retry.skills.skill_library import ALLOWED_SKILLS, available_skills, skill_for_failure_type
from gen_retry.teachers.base import BaseTeacher
from gen_retry.utils.io import read_json, write_json


CONTRACT_SCHEMA_VERSION = "v1"
STOP_REASONS = {
    "passed",
    "max_retry",
    "no_improvement",
    "large_regression",
    "invalid_teacher_action",
    "null",
}


@dataclass(frozen=True)
class StopConfig:
    max_retry: int = 3
    pass_threshold: float = 0.95
    no_improvement_patience: int = 1
    large_regression_score_delta: float = -0.15
    allow_retry_after_regression: bool = False


@dataclass(frozen=True)
class EvalConfig:
    evaluator: str = "geneval2"
    geneval2_command_template: str | None = None
    benchmark_data_path: str | Path | None = None
    aggregate_by: str = "prompt_id"
    atom_threshold: float = 0.5
    eval_result_path: str | Path | None = None


def process_generation_package(
    package_path: str | Path,
    *,
    output_dir: str | Path,
    trajectory_dir: str | Path,
    teacher: BaseTeacher,
    stop_config: StopConfig | None = None,
    eval_config: EvalConfig | None = None,
    resume_trajectory: str | Path | None = None,
) -> dict[str, Any]:
    """Process one Machine A generation package and write Machine B outputs."""

    stop_config = stop_config or StopConfig()
    eval_config = eval_config or EvalConfig()
    package_source = Path(package_path)
    package = read_json(package_source)
    errors = validate_generation_package(package, base_dir=package_source.parent)
    if errors:
        raise ValueError(f"{package_path} is not a valid generation package: {errors}")

    report, raw_eval_path = load_or_run_evaluation(
        package,
        package_base_dir=package_source.parent,
        eval_config=eval_config,
    )
    trajectory_path = (
        Path(resume_trajectory)
        if resume_trajectory
        else trajectory_file_path(package, trajectory_dir=trajectory_dir)
    )
    trajectory = load_or_create_trajectory(package, trajectory_path=trajectory_path)
    seed_attempts_from_retry_history(trajectory, package)

    attempt = build_attempt_from_package(package, report=report, raw_eval_path=raw_eval_path)
    upsert_attempt(trajectory, attempt)
    attempts = sorted(trajectory["attempts"], key=lambda item: int(item.get("round", 0)))
    current_round = int(attempt["round"])
    current_attempt = _attempt_by_round(attempts, current_round)
    memory = build_memory(attempts, current_round=current_round, pass_threshold=stop_config.pass_threshold)
    current_attempt["transition"] = dict(memory["transition"])

    stop = apply_stop_rules(
        attempts,
        current_round=current_round,
        report=report,
        memory=memory,
        config=stop_config,
    )
    teacher_action: dict[str, Any] | None = None
    teacher_error = ""
    if not stop["should_stop"]:
        state = build_teacher_state(
            package,
            trajectory,
            attempts=attempts,
            current_round=current_round,
            report=report,
            memory=memory,
            stop_config=stop_config,
        )
        try:
            action = teacher.retry_replan(state)
            teacher_action = action.to_dict()
        except Exception as exc:  # noqa: BLE001 - caller needs invalid action recorded as data.
            teacher_error = f"{exc.__class__.__name__}: {exc}"
            stop = {
                "should_stop": True,
                "reason": "invalid_teacher_action",
                "details": teacher_error,
            }

    current_attempt["planner_action"] = teacher_action or {}
    trajectory["attempts"] = attempts
    trajectory["memory"] = memory["trajectory_memory"]
    trajectory["latest_round"] = current_round
    trajectory["stop"] = stop
    if teacher_action:
        trajectory["latest_teacher_action"] = teacher_action
    trajectory.setdefault("metadata", {})["last_input_package_path"] = str(package_source)
    trajectory.setdefault("metadata", {})["last_output_package_path"] = str(
        retry_action_file_path(package, output_dir=output_dir)
    )
    write_json(trajectory_path, trajectory)

    output_package = build_retry_action_package(
        package,
        report=report,
        raw_eval_path=raw_eval_path,
        memory=memory,
        stop=stop,
        teacher_action=teacher_action,
        teacher_error=teacher_error,
        trajectory_path=trajectory_path,
    )
    output_path = retry_action_file_path(package, output_dir=output_dir)
    write_json(output_path, output_package)
    return {
        "input_path": str(package_source),
        "output_path": str(output_path),
        "trajectory_path": str(trajectory_path),
        "output_package": output_package,
        "trajectory": trajectory,
    }


def load_or_run_evaluation(
    package: dict[str, Any],
    *,
    package_base_dir: str | Path,
    eval_config: EvalConfig,
) -> tuple[NormalizedEvalReport, str]:
    """Return a normalized report and the source path of the raw eval if any."""

    raw_eval_path = _first_nonempty(
        eval_config.eval_result_path,
        _nested_get(package, ("evaluation", "raw_eval_path")),
        _nested_get(package, ("generation", "raw_eval_path")),
        _nested_get(package, ("generation", "geneval2_result_path")),
        package.get("raw_eval_path"),
        package.get("geneval2_result_path"),
    )
    embedded_eval = package.get("evaluation") or package.get("normalized_eval_report")
    if isinstance(embedded_eval, dict) and _looks_like_normalized_report(embedded_eval):
        return NormalizedEvalReport.from_dict(embedded_eval), str(embedded_eval.get("raw_eval_path", raw_eval_path or ""))

    if raw_eval_path:
        resolved = _resolve_path(raw_eval_path, package_base_dir)
        return load_normalized_eval_report(
            resolved,
            package=package,
            eval_config=eval_config,
        ), str(raw_eval_path)

    if eval_config.evaluator != "geneval2":
        raise ValueError(f"unsupported offline evaluator: {eval_config.evaluator}")
    if not eval_config.geneval2_command_template:
        raise ValueError(
            "No evaluation is available. Provide package.evaluation, package.generation.geneval2_result_path, "
            "--geneval2-result, or --geneval2-command-template."
        )
    image_path_value = str(_nested_get(package, ("generation", "image_path")) or "")
    image_path = str(_resolve_path(image_path_value, package_base_dir))
    adapter = Geneval2Adapter(
        eval_config.geneval2_command_template,
        benchmark_data_path=eval_config.benchmark_data_path,
        aggregate_by=eval_config.aggregate_by,
        atom_threshold=eval_config.atom_threshold,
    )
    report = adapter.evaluate(_original_prompt(package), image_path)
    return report, str(Path(image_path).with_suffix(".geneval2.json"))


def load_normalized_eval_report(
    path: str | Path,
    *,
    package: dict[str, Any],
    eval_config: EvalConfig,
) -> NormalizedEvalReport:
    """Load a normalized report from a raw GenEval2 or already-normalized file."""

    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for key in ("normalized_report", "normalized_eval_report", "evaluation"):
            value = data.get(key)
            if isinstance(value, dict) and _looks_like_normalized_report(value):
                return NormalizedEvalReport.from_dict(value)
        if _looks_like_normalized_report(data):
            return NormalizedEvalReport.from_dict(data)

    rows = load_geneval2_score_rows(source, benchmark_data=eval_config.benchmark_data_path)
    reports = normalize_geneval2_score_list(
        rows,
        aggregate_by=eval_config.aggregate_by,
        atom_threshold=eval_config.atom_threshold,
    )
    return select_report_for_package(reports, package)


def select_report_for_package(
    reports: dict[str, NormalizedEvalReport],
    package: dict[str, Any],
) -> NormalizedEvalReport:
    candidates = [
        package.get("prompt_id"),
        package.get("candidate_id"),
        str(_nested_get(package, ("generation", "image_id")) or ""),
        str(_nested_get(package, ("generation", "image_path")) or ""),
        Path(str(_nested_get(package, ("generation", "image_path")) or "")).name,
        str(_nested_get(package, ("source", "source_index")) or ""),
        _original_prompt(package),
    ]
    for candidate in candidates:
        if candidate not in (None, "") and str(candidate) in reports:
            return reports[str(candidate)]
    if len(reports) == 1:
        return next(iter(reports.values()))
    raise KeyError(
        "could not select GenEval2 report for package; "
        f"tried={candidates}, available_keys={list(reports)[:10]}"
    )


def build_attempt_from_package(
    package: dict[str, Any],
    *,
    report: NormalizedEvalReport,
    raw_eval_path: str,
) -> dict[str, Any]:
    generation = dict(package.get("generation") or {})
    round_id = int(package.get("round", 0))
    return {
        "round": round_id,
        "attempt_type": "initial_generation" if round_id == 0 else "retry_generation",
        "generation": {
            "generator_name": str(generation.get("generator_name", "qwen-image-2512")),
            "prompt_used": str(generation.get("prompt_used", "")),
            "seed": generation.get("seed"),
            "image_id": str(generation.get("image_id", "")),
            "image_path": str(generation.get("image_path", "")),
            "generation_metadata": dict(generation.get("generation_metadata") or {}),
        },
        "previous_action": dict(package.get("previous_action") or {}),
        "evaluation": evaluation_payload(report, raw_eval_path=raw_eval_path),
        "planner_action": {},
        "transition": {},
    }


def load_or_create_trajectory(package: dict[str, Any], *, trajectory_path: str | Path) -> dict[str, Any]:
    path = Path(trajectory_path)
    if path.exists():
        trajectory = read_json(path)
        trajectory.setdefault("attempts", [])
        return trajectory
    source = dict(package.get("source") or {})
    generation = dict(package.get("generation") or {})
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "trajectory_id": str(package.get("trajectory_id", "")),
        "prompt_id": str(package.get("prompt_id", "")),
        "candidate_id": str(package.get("candidate_id", "")),
        "source": source,
        "generator_name": str(generation.get("generator_name", "qwen-image-2512")),
        "initial_plan": dict(package.get("previous_initial_plan") or {}),
        "attempts": [],
        "memory": {},
        "metadata": {"contract": "offline_manual_transfer_v1"},
    }


def seed_attempts_from_retry_history(trajectory: dict[str, Any], package: dict[str, Any]) -> None:
    """Best-effort import of compact retry history when no trajectory exists yet."""

    existing_rounds = {int(item.get("round", 0)) for item in trajectory.get("attempts", []) if isinstance(item, dict)}
    current_round = int(package.get("round", 0))
    for row in package.get("retry_history") or []:
        if not isinstance(row, dict):
            continue
        row_round = int(row.get("round", 0))
        if row_round in existing_rounds or row_round >= current_round:
            continue
        report = NormalizedEvalReport.from_dict(
            {
                "score": row.get("score", 0.0),
                "passed_constraints": row.get("passed_constraints", []),
                "failed_constraints": row.get("failed_constraints", []),
                "uncertain_constraints": row.get("uncertain_constraints", []),
                "critical_failure_types": row.get("critical_failure_types", []),
            }
        )
        trajectory.setdefault("attempts", []).append(
            {
                "round": row_round,
                "attempt_type": "initial_generation" if row_round == 0 else "retry_generation",
                "generation": {
                    "generator_name": row.get("generator_name", ""),
                    "prompt_used": row.get("prompt_used", ""),
                    "seed": row.get("seed"),
                    "image_id": row.get("image_id", ""),
                    "image_path": row.get("image_path", ""),
                    "generation_metadata": {},
                },
                "previous_action": dict(row.get("previous_action") or {}),
                "evaluation": evaluation_payload(report, raw_eval_path=str(row.get("raw_eval_path", ""))),
                "planner_action": dict(row.get("planner_action") or row.get("teacher_action") or {}),
                "transition": dict(row.get("transition") or {}),
            }
        )


def upsert_attempt(trajectory: dict[str, Any], attempt: dict[str, Any]) -> None:
    attempts = [item for item in trajectory.get("attempts", []) if isinstance(item, dict)]
    current_round = int(attempt.get("round", 0))
    replaced = False
    for index, item in enumerate(attempts):
        if int(item.get("round", 0)) == current_round:
            attempts[index] = attempt
            replaced = True
            break
    if not replaced:
        attempts.append(attempt)
    trajectory["attempts"] = sorted(attempts, key=lambda item: int(item.get("round", 0)))


def build_memory(
    attempts: list[dict[str, Any]],
    *,
    current_round: int,
    pass_threshold: float,
) -> dict[str, Any]:
    current = _attempt_by_round(attempts, current_round)
    previous = _previous_attempt(attempts, current_round)
    current_report = _attempt_report(current)
    previous_report = _attempt_report(previous) if previous else None
    best_before = _best_attempt([item for item in attempts if int(item.get("round", 0)) < current_round])
    best_after = _best_attempt([item for item in attempts if int(item.get("round", 0)) <= current_round]) or current
    transition = compute_transition(
        previous_report=previous_report,
        current_report=current_report,
        current_round=current_round,
        pass_threshold=pass_threshold,
    )
    current["transition"] = dict(transition)
    score_delta_from_previous = (
        current_report.score - previous_report.score if previous_report is not None else 0.0
    )
    score_delta_from_best = (
        current_report.score - _attempt_report(best_before).score if best_before else 0.0
    )
    transition["score_delta_from_previous"] = score_delta_from_previous
    transition["score_delta_from_best"] = score_delta_from_best
    best_report = _attempt_report(best_after)
    best_generation = dict(best_after.get("generation") or {})
    memory = {
        "best_so_far_round": int(best_after.get("round", 0)),
        "best_so_far_score": best_report.score,
        "best_so_far_image_path": str(best_generation.get("image_path", "")),
        "best_so_far_prompt": str(best_generation.get("prompt_used", "")),
        "best_so_far_failed_constraints": [
            _constraint_public(item) for item in best_report.failed_constraints
        ],
        "fixed_constraints": transition["fixed_constraints"],
        "persistent_failures": transition["persistent_failures"],
        "new_failures": transition["new_failures"],
        "regressed_constraints": transition["regressed_constraints"],
        "score_delta_from_previous": score_delta_from_previous,
        "score_delta_from_best": score_delta_from_best,
        "retry_history_summary": retry_history_summary(attempts),
    }
    branch_source = "latest" if int(best_after.get("round", 0)) == current_round else "best_so_far"
    return {
        "transition": transition,
        "trajectory_memory": memory,
        "best_so_far": {
            "round": memory["best_so_far_round"],
            "score": memory["best_so_far_score"],
            "image_path": memory["best_so_far_image_path"],
            "prompt": memory["best_so_far_prompt"],
            "failed_constraints": memory["best_so_far_failed_constraints"],
        },
        "branch_source": branch_source,
        "branch_source_round": memory["best_so_far_round"] if branch_source == "best_so_far" else current_round,
    }


def compute_transition(
    *,
    previous_report: NormalizedEvalReport | None,
    current_report: NormalizedEvalReport,
    current_round: int,
    pass_threshold: float,
) -> dict[str, Any]:
    if previous_report is None:
        return {
            "score_delta_from_previous": 0.0,
            "score_delta_from_best": 0.0,
            "fixed_constraints": [],
            "persistent_failures": [],
            "new_failures": [_constraint_public(item) for item in current_report.failed_constraints],
            "regressed_constraints": [],
            "transition_type": "initial",
        }

    previous_failed = {_constraint_key(item): item for item in previous_report.failed_constraints}
    previous_passed = {_constraint_key(item): item for item in previous_report.passed_constraints}
    current_failed = {_constraint_key(item): item for item in current_report.failed_constraints}
    current_passed = {_constraint_key(item): item for item in current_report.passed_constraints}
    fixed: list[dict[str, Any]] = []
    for key in sorted(set(previous_failed) - set(current_failed)):
        source = current_passed.get(key, previous_failed[key])
        item = _constraint_public(source)
        item["status"] = "fixed" if key not in current_passed else item.get("status", "passed")
        fixed.append(item)
    persistent = [
        _constraint_public(current_failed[key]) for key in sorted(set(previous_failed) & set(current_failed))
    ]
    new = [
        _constraint_public(current_failed[key]) for key in sorted(set(current_failed) - set(previous_failed))
    ]
    regressed = [
        _constraint_public(current_failed[key]) for key in sorted(set(previous_passed) & set(current_failed))
    ]
    if is_passed(current_report, pass_threshold):
        transition_type = "passed_after_retry"
    elif regressed or current_report.score < previous_report.score:
        transition_type = "regressed"
    elif fixed or current_report.score > previous_report.score or (
        len(current_report.failed_constraints) < len(previous_report.failed_constraints)
    ):
        transition_type = "improved_after_retry"
    else:
        transition_type = "no_improvement"
    return {
        "score_delta_from_previous": current_report.score - previous_report.score,
        "score_delta_from_best": 0.0,
        "fixed_constraints": fixed,
        "persistent_failures": persistent,
        "new_failures": new,
        "regressed_constraints": regressed,
        "transition_type": transition_type if current_round > 0 else "initial",
    }


def apply_stop_rules(
    attempts: list[dict[str, Any]],
    *,
    current_round: int,
    report: NormalizedEvalReport,
    memory: dict[str, Any],
    config: StopConfig,
) -> dict[str, Any]:
    if is_passed(report, config.pass_threshold):
        return {"should_stop": True, "reason": "passed"}
    if current_round >= config.max_retry:
        return {"should_stop": True, "reason": "max_retry"}
    delta = float(memory["trajectory_memory"].get("score_delta_from_previous", 0.0))
    if (
        current_round > 0
        and not config.allow_retry_after_regression
        and delta <= config.large_regression_score_delta
    ):
        return {
            "should_stop": True,
            "reason": "large_regression",
            "score_delta_from_previous": delta,
        }
    if current_round > 0 and config.no_improvement_patience > 0:
        stagnant = _consecutive_transition_count(attempts, {"no_improvement"})
        if stagnant >= config.no_improvement_patience:
            return {
                "should_stop": True,
                "reason": "no_improvement",
                "no_improvement_rounds": stagnant,
            }
    return {"should_stop": False, "reason": "null"}


def build_teacher_state(
    package: dict[str, Any],
    trajectory: dict[str, Any],
    *,
    attempts: list[dict[str, Any]],
    current_round: int,
    report: NormalizedEvalReport,
    memory: dict[str, Any],
    stop_config: StopConfig,
) -> dict[str, Any]:
    current = _attempt_by_round(attempts, current_round)
    current_generation = dict(current.get("generation") or {})
    previous_action = dict(package.get("previous_action") or current.get("previous_action") or {})
    selected_skills = previous_selected_skills(previous_action, package)
    return {
        "trajectory_id": str(package.get("trajectory_id", "")),
        "prompt_id": str(package.get("prompt_id", "")),
        "candidate_id": str(package.get("candidate_id", "")),
        "original_prompt": _original_prompt(package),
        "previous_initial_plan": _previous_initial_plan(package, trajectory, selected_skills),
        "previous_action": previous_action,
        "previous_prompt": str(current_generation.get("prompt_used", "")),
        "previous_selected_skills": selected_skills,
        "current_round": current_round,
        "retry_round": current_round,
        "retry_budget_left": max(0, stop_config.max_retry - current_round),
        "normalized_eval_report": _report_public(report),
        "current_eval_report": _report_public(report),
        "retry_history": compact_retry_history(attempts),
        "memory": {
            "best_so_far": memory["best_so_far"],
            "fixed_constraints": memory["trajectory_memory"]["fixed_constraints"],
            "persistent_failures": memory["trajectory_memory"]["persistent_failures"],
            "new_failures": memory["trajectory_memory"]["new_failures"],
            "regressed_constraints": memory["trajectory_memory"]["regressed_constraints"],
            "score_delta_from_previous": memory["trajectory_memory"]["score_delta_from_previous"],
            "score_delta_from_best": memory["trajectory_memory"]["score_delta_from_best"],
        },
        "best_so_far": memory["best_so_far"],
        "fixed_constraints": memory["trajectory_memory"]["fixed_constraints"],
        "persistent_failures": memory["trajectory_memory"]["persistent_failures"],
        "new_failures": memory["trajectory_memory"]["new_failures"],
        "regressed_constraints": memory["trajectory_memory"]["regressed_constraints"],
        "score_delta_from_previous": memory["trajectory_memory"]["score_delta_from_previous"],
        "score_delta_from_best": memory["trajectory_memory"]["score_delta_from_best"],
        "branch_source": memory["branch_source"],
        "branch_source_round": memory["branch_source_round"],
        "available_skills": available_skills(),
    }


def build_retry_action_package(
    package: dict[str, Any],
    *,
    report: NormalizedEvalReport,
    raw_eval_path: str,
    memory: dict[str, Any],
    stop: dict[str, Any],
    teacher_action: dict[str, Any] | None,
    teacher_error: str,
    trajectory_path: str | Path,
) -> dict[str, Any]:
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "trajectory_id": str(package.get("trajectory_id", "")),
        "prompt_id": str(package.get("prompt_id", "")),
        "candidate_id": str(package.get("candidate_id", "")),
        "round": int(package.get("round", 0)),
        "evaluation": evaluation_payload(report, raw_eval_path=raw_eval_path),
        "memory": dict(memory["trajectory_memory"]),
        "stop": dict(stop),
        "teacher_action": teacher_action,
        "teacher_error": teacher_error,
        "trajectory_path": str(trajectory_path),
    }


def evaluation_payload(report: NormalizedEvalReport, *, raw_eval_path: str) -> dict[str, Any]:
    payload = _report_public(report)
    payload["passed"] = is_passed(report)
    payload["raw_eval_path"] = raw_eval_path
    payload["raw_report"] = report.raw_report or {}
    return payload


def retry_history_summary(attempts: list[dict[str, Any]]) -> str:
    parts = []
    for attempt in sorted(attempts, key=lambda item: int(item.get("round", 0))):
        report = _attempt_report(attempt)
        failed = [item["target"] for item in (_constraint_public(c) for c in report.failed_constraints)]
        transition = str((attempt.get("transition") or {}).get("transition_type", ""))
        parts.append(
            f"round={int(attempt.get('round', 0))} score={report.score:.3f} "
            f"failed={failed} transition={transition}"
        )
    return " | ".join(parts)


def compact_retry_history(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for attempt in sorted(attempts, key=lambda item: int(item.get("round", 0))):
        generation = dict(attempt.get("generation") or {})
        report = _attempt_report(attempt)
        history.append(
            {
                "round": int(attempt.get("round", 0)),
                "attempt_type": str(attempt.get("attempt_type", "")),
                "prompt_used": str(generation.get("prompt_used", "")),
                "score": report.score,
                "passed_constraints": [_constraint_public(item) for item in report.passed_constraints],
                "failed_constraints": [_constraint_public(item) for item in report.failed_constraints],
                "uncertain_constraints": [_constraint_public(item) for item in report.uncertain_constraints],
                "critical_failure_types": list(report.critical_failure_types),
                "transition": dict(attempt.get("transition") or {}),
                "previous_action": dict(attempt.get("previous_action") or {}),
                "planner_action": dict(attempt.get("planner_action") or {}),
            }
        )
    return history


def previous_selected_skills(previous_action: dict[str, Any], package: dict[str, Any]) -> list[str]:
    if previous_action.get("action_type") == "retry_replan":
        skills = previous_action.get("skill_revision", {}).get("new_skills", [])
        return _valid_skills(skills)
    if previous_action.get("action_type") == "initial_plan":
        return _valid_skills(previous_action.get("selected_skills", []))
    source_skills = _nested_get(package, ("source", "skills"))
    mapped = [_map_source_skill(str(item)) for item in source_skills or []]
    return _valid_skills(mapped)


def is_passed(report: NormalizedEvalReport, pass_threshold: float = 0.95) -> bool:
    if not report.failed_constraints:
        return True
    return report.score >= pass_threshold and not report.critical_failure_types


def validate_generation_package(data: dict[str, Any], *, base_dir: str | Path) -> list[str]:
    errors: list[str] = []
    _require_keys(data, ("schema_version", "trajectory_id", "prompt_id", "candidate_id", "round", "source", "generation"), errors)
    if data.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        errors.append("schema_version must be v1")
    generation = data.get("generation")
    if not isinstance(generation, dict):
        errors.append("generation must be an object")
        return errors
    _require_keys(generation, ("generator_name", "prompt_used", "image_path"), errors, prefix="generation.")
    image_path = str(generation.get("image_path", ""))
    if image_path and not _resolve_path(image_path, base_dir).exists():
        errors.append(f"generation.image_path does not exist: {image_path}")
    if data.get("previous_action") not in (None, {}) and not isinstance(data.get("previous_action"), dict):
        errors.append("previous_action must be null or an object")
    if not isinstance(data.get("retry_history", []), list):
        errors.append("retry_history must be a list")
    return errors


def validate_retry_action_package(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    _require_keys(data, ("schema_version", "trajectory_id", "prompt_id", "candidate_id", "round", "evaluation", "memory", "stop"), errors)
    if data.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        errors.append("schema_version must be v1")
    evaluation = data.get("evaluation")
    if not isinstance(evaluation, dict) or not _looks_like_normalized_report(evaluation):
        errors.append("evaluation must be a normalized eval report")
    else:
        try:
            NormalizedEvalReport.from_dict(evaluation)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"evaluation is not normalized: {exc}")
    stop = data.get("stop")
    if not isinstance(stop, dict):
        errors.append("stop must be an object")
    else:
        reason = str(stop.get("reason", ""))
        if reason not in STOP_REASONS:
            errors.append(f"stop.reason must be one of {sorted(STOP_REASONS)}")
        if not stop.get("should_stop", False):
            action = data.get("teacher_action")
            if not isinstance(action, dict):
                errors.append("teacher_action is required when stop.should_stop is false")
            else:
                try:
                    RetryReplanAction.from_dict(action)
                except (ActionValidationError, ValueError) as exc:
                    errors.append(f"teacher_action is invalid: {exc}")
                if not str(action.get("retry_prompt", "")).strip():
                    errors.append("teacher_action.retry_prompt is required when stop.should_stop is false")
    memory = data.get("memory")
    required_memory = (
        "best_so_far_round",
        "best_so_far_score",
        "best_so_far_image_path",
        "best_so_far_prompt",
        "best_so_far_failed_constraints",
        "fixed_constraints",
        "persistent_failures",
        "new_failures",
        "regressed_constraints",
        "score_delta_from_previous",
        "score_delta_from_best",
    )
    if not isinstance(memory, dict):
        errors.append("memory must be an object")
    else:
        _require_keys(memory, required_memory, errors, prefix="memory.")
    return errors


def validate_raw_trajectory(data: dict[str, Any], *, base_dir: str | Path, pass_threshold: float = 0.95) -> list[str]:
    errors: list[str] = []
    _require_keys(data, ("schema_version", "trajectory_id", "prompt_id", "candidate_id", "attempts", "memory"), errors)
    attempts = data.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        errors.append("attempts must be a non-empty list")
        return errors
    for index, attempt in enumerate(attempts):
        if not isinstance(attempt, dict):
            errors.append(f"attempts[{index}] must be an object")
            continue
        _require_keys(
            attempt,
            ("round", "attempt_type", "generation", "evaluation", "planner_action", "transition"),
            errors,
            prefix=f"attempts[{index}].",
        )
        generation = attempt.get("generation")
        if isinstance(generation, dict):
            image_path = str(generation.get("image_path", ""))
            if image_path and not _resolve_path(image_path, base_dir).exists():
                errors.append(f"attempts[{index}].generation.image_path does not exist: {image_path}")
        evaluation = attempt.get("evaluation")
        if isinstance(evaluation, dict):
            try:
                NormalizedEvalReport.from_dict(evaluation)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"attempts[{index}].evaluation is invalid: {exc}")
    sorted_attempts = sorted(
        [item for item in attempts if isinstance(item, dict)],
        key=lambda item: int(item.get("round", 0)),
    )
    latest_round = int(sorted_attempts[-1].get("round", 0))
    try:
        recomputed = build_memory(sorted_attempts, current_round=latest_round, pass_threshold=pass_threshold)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"could not recompute memory: {exc}")
        return errors
    memory = data.get("memory") if isinstance(data.get("memory"), dict) else {}
    for key in (
        "best_so_far_round",
        "best_so_far_score",
        "fixed_constraints",
        "persistent_failures",
        "new_failures",
        "regressed_constraints",
    ):
        if memory.get(key) != recomputed["trajectory_memory"].get(key):
            errors.append(f"memory.{key} does not match recomputed value")
    return errors


def validate_offline_object(data: dict[str, Any], *, base_dir: str | Path = ".") -> list[str]:
    if "attempts" in data:
        return validate_raw_trajectory(data, base_dir=base_dir)
    if "stop" in data and "evaluation" in data:
        return validate_retry_action_package(data)
    if "generation" in data and "source" in data:
        return validate_generation_package(data, base_dir=base_dir)
    return ["unknown offline contract object type"]


def trajectory_file_path(package: dict[str, Any], *, trajectory_dir: str | Path) -> Path:
    name = _safe_name(f"{package.get('trajectory_id', 'trajectory')}__{package.get('candidate_id', 'candidate')}")
    return Path(trajectory_dir) / f"{name}.json"


def retry_action_file_path(package: dict[str, Any], *, output_dir: str | Path) -> Path:
    name = _safe_name(
        f"{package.get('trajectory_id', 'trajectory')}__{package.get('candidate_id', 'candidate')}"
        f"__round_{int(package.get('round', 0))}_retry_action_package"
    )
    return Path(output_dir) / f"{name}.json"


def _attempt_by_round(attempts: list[dict[str, Any]], round_id: int) -> dict[str, Any]:
    for attempt in attempts:
        if int(attempt.get("round", 0)) == round_id:
            return attempt
    raise KeyError(f"missing attempt round {round_id}")


def _previous_attempt(attempts: list[dict[str, Any]], round_id: int) -> dict[str, Any] | None:
    previous = [item for item in attempts if int(item.get("round", 0)) < round_id]
    if not previous:
        return None
    return sorted(previous, key=lambda item: int(item.get("round", 0)))[-1]


def _best_attempt(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for attempt in attempts:
        if best is None:
            best = attempt
            continue
        report = _attempt_report(attempt)
        best_report = _attempt_report(best)
        if report.score > best_report.score:
            best = attempt
        elif report.score == best_report.score and len(report.failed_constraints) < len(best_report.failed_constraints):
            best = attempt
    return best


def _attempt_report(attempt: dict[str, Any] | None) -> NormalizedEvalReport:
    if not attempt:
        raise ValueError("attempt is required")
    return NormalizedEvalReport.from_dict(dict(attempt.get("evaluation") or {}))


def _constraint_key(constraint: NormalizedConstraint) -> str:
    data = constraint.to_dict()
    return "|".join(
        [
            str(data.get("type", "")),
            str(data.get("target", "")),
            json.dumps(data.get("expected"), ensure_ascii=False, sort_keys=True),
        ]
    )


def _constraint_public(constraint: NormalizedConstraint) -> dict[str, Any]:
    data = constraint.to_dict()
    details = data.get("details")
    if isinstance(details, dict):
        data["details"] = {
            key: value
            for key, value in details.items()
            if key
            not in {
                "raw",
                "image_path",
                "image_id",
                "prompt_id",
                "sample_id",
                "id",
            }
        }
    return data


def _report_public(report: NormalizedEvalReport) -> dict[str, Any]:
    return {
        "score": report.score,
        "passed_constraints": [_constraint_public(item) for item in report.passed_constraints],
        "failed_constraints": [_constraint_public(item) for item in report.failed_constraints],
        "uncertain_constraints": [_constraint_public(item) for item in report.uncertain_constraints],
        "critical_failure_types": list(report.critical_failure_types),
    }


def _consecutive_transition_count(attempts: list[dict[str, Any]], transition_types: set[str]) -> int:
    count = 0
    for attempt in reversed(sorted(attempts, key=lambda item: int(item.get("round", 0)))):
        transition = str((attempt.get("transition") or {}).get("transition_type", ""))
        if transition in transition_types:
            count += 1
        elif transition != "initial":
            break
    return count


def _previous_initial_plan(package: dict[str, Any], trajectory: dict[str, Any], selected_skills: list[str]) -> dict[str, Any]:
    if isinstance(package.get("previous_initial_plan"), dict) and package["previous_initial_plan"]:
        return dict(package["previous_initial_plan"])
    if isinstance(trajectory.get("initial_plan"), dict) and trajectory["initial_plan"]:
        return dict(trajectory["initial_plan"])
    return {
        "action_type": "initial_plan",
        "parsed_constraints": {"objects": [], "counts": {}, "attributes": {}, "relations": []},
        "selected_skills": selected_skills,
        "generation_strategy": "",
        "initial_prompt": str(_nested_get(package, ("generation", "prompt_used")) or ""),
        "generation_guards": [],
    }


def _map_source_skill(skill: str) -> str:
    skill = skill.strip().lower()
    if skill == "count":
        return "quantity_counting"
    if skill in {"attribute", "color"}:
        return "attribute_binding"
    if skill in {"position", "spatial", "relation", "verb"}:
        return "spatial_layout"
    if skill in {"object", "presence"}:
        return "object_presence"
    if skill in {"negative", "forbidden"}:
        return "negative_constraints"
    return skill_for_failure_type(skill)


def _valid_skills(skills: Any) -> list[str]:
    out: list[str] = []
    for skill in skills or []:
        value = str(skill).strip()
        if value in ALLOWED_SKILLS and value not in out:
            out.append(value)
    return out


def _looks_like_normalized_report(data: dict[str, Any]) -> bool:
    return "score" in data and (
        "failed_constraints" in data or "passed_constraints" in data or "uncertain_constraints" in data
    )


def _original_prompt(package: dict[str, Any]) -> str:
    return str(
        _nested_get(package, ("source", "original_prompt"))
        or package.get("original_prompt")
        or _nested_get(package, ("generation", "prompt_used"))
        or ""
    )


def _nested_get(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _resolve_path(path: str | Path, base_dir: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else Path(base_dir) / value


def _require_keys(data: dict[str, Any], keys: tuple[str, ...], errors: list[str], *, prefix: str = "") -> None:
    for key in keys:
        if key not in data:
            errors.append(f"missing required field: {prefix}{key}")


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("._") or "package"
