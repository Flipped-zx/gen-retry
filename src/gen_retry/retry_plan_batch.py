"""Batch orchestration for GenEval2 diagnostics to retry plans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any

from gen_retry.offline_package_builder import build_generation_packages_from_manifest
from gen_retry.offline_planner import (
    EvalConfig,
    StopConfig,
    process_generation_package,
    retry_action_file_path,
    trajectory_file_path,
)
from gen_retry.quality.geneval2_retry_inputs import check_geneval2_retry_inputs
from gen_retry.quality.retry_plan_quality import check_retry_plan_packages
from gen_retry.teachers.base import BaseTeacher
from gen_retry.teachers.gpt55_teacher_adapter import GPT55TeacherAdapter
from gen_retry.teachers.mock_teacher import MockTeacher
from gen_retry.teachers.seed_teacher_adapter import SeedTeacherAdapter
from gen_retry.utils.io import read_jsonl, write_json, write_jsonl


@dataclass(frozen=True)
class RetryPlanBatchConfig:
    manifest_path: str | Path | None
    package_dir: str | Path
    output_dir: str | Path
    trajectory_dir: str | Path
    initial_plan_dir: str | Path | None = None
    eval_results_path: str | Path | None = None
    diagnostic_jobs_path: str | Path | None = None
    benchmark_data_path: str | Path | None = None
    aggregate_by: str = "candidate_id"
    atom_threshold: float = 0.5
    candidate_index: int | None = 0
    all_candidates: bool = False
    limit: int | None = None
    round_id: int = 0
    generator_name: str = "qwen-image-2512"
    require_initial_plan: bool = True
    allow_missing_eval: bool = False
    resume: bool = False
    max_retry: int = 3
    pass_threshold: float = 0.95
    no_improvement_patience: int = 1
    large_regression_score_delta: float = -0.15
    allow_retry_after_regression: bool = False


def run_retry_plan_batch(
    config: RetryPlanBatchConfig,
    *,
    teacher: BaseTeacher,
) -> dict[str, Any]:
    """Build/evaluate packages and write retry action packages in one batch."""

    started = time.time()
    package_dir = Path(config.package_dir)
    output_dir = Path(config.output_dir)
    trajectory_dir = Path(config.trajectory_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    trajectory_dir.mkdir(parents=True, exist_ok=True)

    package_build: dict[str, Any] | None = None
    input_preflight: dict[str, Any] | None = None
    package_manifest_path: str | Path | None = None
    if config.manifest_path:
        build_summary = build_generation_packages_from_manifest(
            manifest_path=config.manifest_path,
            output_dir=package_dir,
            initial_plan_dir=config.initial_plan_dir,
            eval_results_path=config.eval_results_path,
            benchmark_data_path=config.benchmark_data_path,
            aggregate_by=config.aggregate_by,
            atom_threshold=config.atom_threshold,
            candidate_index=config.candidate_index,
            all_candidates=config.all_candidates,
            limit=config.limit,
            round_id=config.round_id,
            generator_name=config.generator_name,
            require_initial_plan=config.require_initial_plan,
        )
        package_build = build_summary.to_dict()
        package_manifest_path = build_summary.package_manifest_path
        if build_summary.missing_eval_report_count and not config.allow_missing_eval:
            summary = _base_summary(config, started=started, teacher=teacher)
            summary["package_build"] = package_build
            summary["status"] = "error"
            summary["errors"] = [
                f"missing normalized eval report for {build_summary.missing_eval_report_count} package(s)"
            ]
            write_json(output_dir / "batch_summary.json", summary)
            return summary
    else:
        existing_manifest = package_dir / "package_manifest.jsonl"
        if existing_manifest.exists():
            package_manifest_path = existing_manifest

    if config.eval_results_path and package_manifest_path and not config.allow_missing_eval:
        input_preflight = check_geneval2_retry_inputs(
            package_manifest_path=package_manifest_path,
            diagnostic_jobs_path=config.diagnostic_jobs_path,
            eval_results_path=config.eval_results_path,
            expected_count=config.limit,
            output_path=output_dir / "retry_input_preflight.json",
        )
        if input_preflight["critical_count"]:
            summary = _base_summary(config, started=started, teacher=teacher)
            summary["package_build"] = package_build
            summary["input_preflight"] = {
                key: value
                for key, value in input_preflight.items()
                if key != "issues"
            }
            summary["status"] = "error"
            summary["errors"] = ["retry input preflight failed"]
            summary["retry_input_preflight_path"] = str(output_dir / "retry_input_preflight.json")
            write_json(output_dir / "batch_summary.json", summary)
            return summary

    package_paths = _package_paths(package_dir)
    stop_config = StopConfig(
        max_retry=config.max_retry,
        pass_threshold=config.pass_threshold,
        no_improvement_patience=config.no_improvement_patience,
        large_regression_score_delta=config.large_regression_score_delta,
        allow_retry_after_regression=config.allow_retry_after_regression,
    )
    eval_config = EvalConfig(
        evaluator="geneval2",
        benchmark_data_path=config.benchmark_data_path,
        aggregate_by=config.aggregate_by,
        atom_threshold=config.atom_threshold,
    )

    retry_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for package_path in package_paths:
        try:
            if config.resume and _output_exists(package_path, output_dir=output_dir, trajectory_dir=trajectory_dir):
                skipped.append({"package_path": str(package_path), "reason": "existing_output"})
                continue
            result = process_generation_package(
                package_path,
                output_dir=output_dir,
                trajectory_dir=trajectory_dir,
                teacher=teacher,
                stop_config=stop_config,
                eval_config=eval_config,
            )
            output = result["output_package"]
            retry_rows.append(
                {
                    "package_path": str(package_path),
                    "output_path": result["output_path"],
                    "trajectory_path": result["trajectory_path"],
                    "trajectory_id": output.get("trajectory_id", ""),
                    "prompt_id": output.get("prompt_id", ""),
                    "candidate_id": output.get("candidate_id", ""),
                    "round": output.get("round", 0),
                    "stop": output.get("stop", {}),
                    "has_teacher_request": isinstance(output.get("teacher_request"), dict),
                    "has_teacher_action": isinstance(output.get("teacher_action"), dict),
                    "teacher_error": output.get("teacher_error", ""),
                }
            )
        except Exception as exc:  # noqa: BLE001 - failures are batch data.
            failures.append(
                {
                    "package_path": str(package_path),
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                }
            )

    write_jsonl(output_dir / "retry_action_manifest.jsonl", retry_rows)
    write_jsonl(output_dir / "batch_failures.jsonl", failures)
    write_jsonl(output_dir / "batch_skipped.jsonl", skipped)
    quality_packages = []
    for row in retry_rows:
        output_path = row.get("output_path")
        if output_path:
            import json

            path = Path(str(output_path))
            quality_packages.append((str(path), json.loads(path.read_text(encoding="utf-8"))))
    quality_report = check_retry_plan_packages(quality_packages)
    write_json(output_dir / "retry_plan_quality_report.json", quality_report)
    summary = _base_summary(config, started=started, teacher=teacher)
    summary.update(
        {
            "status": "ok" if not failures and not quality_report["critical_count"] else "error",
            "package_build": package_build,
            "input_preflight": (
                {key: value for key, value in input_preflight.items() if key != "issues"}
                if input_preflight
                else None
            ),
            "packages_seen": len(package_paths),
            "retry_actions_written": len(retry_rows),
            "failed": len(failures),
            "skipped": len(skipped),
            "quality_status": quality_report["status"],
            "quality_critical_count": quality_report["critical_count"],
            "quality_warning_count": quality_report["warning_count"],
            "retry_action_manifest_path": str(output_dir / "retry_action_manifest.jsonl"),
            "batch_failures_path": str(output_dir / "batch_failures.jsonl"),
            "batch_skipped_path": str(output_dir / "batch_skipped.jsonl"),
            "retry_plan_quality_report_path": str(output_dir / "retry_plan_quality_report.json"),
            "retry_input_preflight_path": str(output_dir / "retry_input_preflight.json") if input_preflight else "",
            "elapsed_seconds": time.time() - started,
        }
    )
    write_json(output_dir / "batch_summary.json", summary)
    return summary


def teacher_from_name(name: str) -> BaseTeacher:
    if name == "mock":
        return MockTeacher()
    if name == "seed":
        return SeedTeacherAdapter()
    if name == "gpt55":
        return GPT55TeacherAdapter()
    raise ValueError(f"unknown teacher: {name}")


def _package_paths(package_dir: Path) -> list[Path]:
    manifest = package_dir / "package_manifest.jsonl"
    if manifest.exists():
        paths = []
        for row in read_jsonl(manifest):
            value = row.get("package_path")
            if value:
                paths.append(Path(str(value)))
        return sorted(paths)
    return sorted(package_dir.glob("*_generation_package.json"))


def _output_exists(package_path: Path, *, output_dir: Path, trajectory_dir: Path) -> bool:
    import json

    package = json.loads(package_path.read_text(encoding="utf-8"))
    if not isinstance(package, dict):
        return False
    return retry_action_file_path(package, output_dir=output_dir).exists() and trajectory_file_path(
        package,
        trajectory_dir=trajectory_dir,
    ).exists()


def _base_summary(
    config: RetryPlanBatchConfig,
    *,
    started: float,
    teacher: BaseTeacher,
) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "started_at_unix": started,
        "teacher": getattr(teacher, "name", teacher.__class__.__name__),
        "manifest_path": str(config.manifest_path or ""),
        "package_dir": str(config.package_dir),
        "output_dir": str(config.output_dir),
        "trajectory_dir": str(config.trajectory_dir),
        "eval_results_path": str(config.eval_results_path or ""),
        "diagnostic_jobs_path": str(config.diagnostic_jobs_path or ""),
        "candidate_index": config.candidate_index,
        "limit": config.limit,
        "allow_missing_eval": config.allow_missing_eval,
        "resume": config.resume,
        "teacher_uses_image_bytes": False,
    }
