"""Build no-API teacher request previews from offline retry packages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gen_retry.offline_planner import (
    EvalConfig,
    StopConfig,
    apply_stop_rules,
    build_attempt_from_package,
    build_memory,
    build_teacher_state,
    load_or_create_trajectory,
    load_or_run_evaluation,
    seed_attempts_from_retry_history,
    trajectory_file_path,
    upsert_attempt,
    validate_generation_package,
)
from gen_retry.quality.retry_plan_quality import FORBIDDEN_IMAGE_INPUT_KEYS
from gen_retry.utils.io import read_json, read_jsonl, write_json, write_jsonl


@dataclass(frozen=True)
class TeacherRequestPreviewConfig:
    package_manifest_path: str | Path | None = None
    package_dir: str | Path | None = None
    output_path: str | Path = "teacher_requests_preview.jsonl"
    summary_path: str | Path | None = None
    trajectory_dir: str | Path | None = None
    max_retry: int = 3
    pass_threshold: float = 0.95
    no_improvement_patience: int = 1
    large_regression_score_delta: float = -0.15
    allow_retry_after_regression: bool = False
    aggregate_by: str = "candidate_id"
    atom_threshold: float = 0.9


def preview_teacher_requests(config: TeacherRequestPreviewConfig) -> dict[str, Any]:
    package_paths = _package_paths(config)
    output_path = Path(config.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path = Path(config.summary_path) if config.summary_path else output_path.with_suffix(".summary.json")

    stop_config = StopConfig(
        max_retry=config.max_retry,
        pass_threshold=config.pass_threshold,
        no_improvement_patience=config.no_improvement_patience,
        large_regression_score_delta=config.large_regression_score_delta,
        allow_retry_after_regression=config.allow_retry_after_regression,
    )
    eval_config = EvalConfig(
        evaluator="geneval2",
        aggregate_by=config.aggregate_by,
        atom_threshold=config.atom_threshold,
    )

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for package_path in package_paths:
        try:
            rows.append(_preview_one(package_path, config=config, stop_config=stop_config, eval_config=eval_config))
        except Exception as exc:  # noqa: BLE001 - preview should report all bad packages.
            failures.append(
                {
                    "package_path": str(package_path),
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                }
            )

    write_jsonl(output_path, rows)
    request_rows = [row for row in rows if isinstance(row.get("teacher_request"), dict)]
    forbidden_rows = [
        {
            "candidate_id": row.get("candidate_id", ""),
            "package_path": row.get("package_path", ""),
            "forbidden_keys": sorted(FORBIDDEN_IMAGE_INPUT_KEYS & _deep_keys(row.get("teacher_request"))),
        }
        for row in request_rows
        if FORBIDDEN_IMAGE_INPUT_KEYS & _deep_keys(row.get("teacher_request"))
    ]
    stopped = sum(1 for row in rows if row.get("stop", {}).get("should_stop") is True)
    summary = {
        "schema_version": "v1",
        "status": "fail" if failures or forbidden_rows else "pass",
        "packages_seen": len(package_paths),
        "preview_rows_written": len(rows),
        "teacher_requests_written": len(request_rows),
        "stopped_without_request": stopped,
        "failed": len(failures),
        "output_path": str(output_path),
        "summary_path": str(summary_path),
        "teacher_uses_image_bytes": False,
        "forbidden_image_input_key_rows": forbidden_rows,
        "failures": failures,
    }
    write_json(summary_path, summary)
    return summary


def _preview_one(
    package_path: Path,
    *,
    config: TeacherRequestPreviewConfig,
    stop_config: StopConfig,
    eval_config: EvalConfig,
) -> dict[str, Any]:
    package = read_json(package_path)
    errors = validate_generation_package(
        package,
        base_dir=package_path.parent,
        require_image_path_exists=False,
    )
    if errors:
        raise ValueError(f"invalid generation package: {errors}")

    report, raw_eval_path = load_or_run_evaluation(
        package,
        package_base_dir=package_path.parent,
        eval_config=eval_config,
    )
    trajectory_dir = Path(config.trajectory_dir) if config.trajectory_dir else package_path.parent
    trajectory = load_or_create_trajectory(
        package,
        trajectory_path=trajectory_file_path(package, trajectory_dir=trajectory_dir),
    )
    seed_attempts_from_retry_history(trajectory, package)
    attempt = build_attempt_from_package(package, report=report, raw_eval_path=raw_eval_path)
    upsert_attempt(trajectory, attempt)
    attempts = sorted(trajectory["attempts"], key=lambda item: int(item.get("round", 0)))
    current_round = int(attempt["round"])
    memory = build_memory(attempts, current_round=current_round, pass_threshold=stop_config.pass_threshold)
    stop = apply_stop_rules(
        attempts,
        current_round=current_round,
        report=report,
        memory=memory,
        config=stop_config,
    )
    request = None
    if not stop["should_stop"]:
        request = build_teacher_state(
            package,
            trajectory,
            attempts=attempts,
            current_round=current_round,
            report=report,
            memory=memory,
            stop_config=stop_config,
        )
    return {
        "package_path": str(package_path),
        "trajectory_id": str(package.get("trajectory_id", "")),
        "prompt_id": str(package.get("prompt_id", "")),
        "candidate_id": str(package.get("candidate_id", "")),
        "round": int(package.get("round", 0)),
        "score": report.score,
        "failed_constraints": len(report.failed_constraints),
        "critical_failure_types": list(report.critical_failure_types),
        "stop": stop,
        "teacher_request": request,
    }


def _package_paths(config: TeacherRequestPreviewConfig) -> list[Path]:
    if bool(config.package_manifest_path) == bool(config.package_dir):
        raise ValueError("provide exactly one of package_manifest_path or package_dir")
    if config.package_manifest_path:
        paths: list[Path] = []
        for row in read_jsonl(config.package_manifest_path):
            value = row.get("package_path")
            if value:
                paths.append(Path(str(value)))
        return sorted(paths)
    package_dir = Path(str(config.package_dir))
    manifest = package_dir / "package_manifest.jsonl"
    if manifest.exists():
        return _package_paths(TeacherRequestPreviewConfig(package_manifest_path=manifest))
    return sorted(package_dir.glob("*_generation_package.json"))


def _deep_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key))
            keys.update(_deep_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_deep_keys(item))
    return keys
