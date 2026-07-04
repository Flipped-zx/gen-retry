"""Prepare GenEval2 diagnostics for teacher retry planning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gen_retry.evaluators.geneval2_result_normalizer import (
    load_geneval2_score_rows,
    normalize_geneval2_score_list,
)
from gen_retry.offline_package_builder import build_generation_packages_from_manifest
from gen_retry.quality.geneval2_retry_inputs import check_geneval2_retry_inputs
from gen_retry.utils.io import write_json, write_jsonl


@dataclass(frozen=True)
class Geneval2RetryPrepareConfig:
    manifest_path: str | Path
    package_dir: str | Path
    initial_plan_dir: str | Path
    diagnostic_jobs_path: str | Path
    eval_results_path: str | Path | None = None
    raw_score_lists_path: str | Path | None = None
    benchmark_data_path: str | Path | None = None
    normalized_output_path: str | Path | None = None
    summary_path: str | Path | None = None
    preflight_output_path: str | Path | None = None
    aggregate_by: str = "candidate_id"
    atom_threshold: float = 0.9
    candidate_index: int | None = 0
    all_candidates: bool = False
    limit: int | None = 100
    round_id: int = 0
    generator_name: str = "qwen-image-2512"
    require_initial_plan: bool = True


def prepare_geneval2_retry_inputs(config: Geneval2RetryPrepareConfig) -> dict[str, Any]:
    """Normalize returned diagnostics, rebuild packages, and preflight inputs.

    This function intentionally stops before teacher API calls. Its output is
    the safe handoff point: package rows now contain normalized GenEval2 reports
    paired with the initial-plan context, and preflight proves candidate-level
    coverage before retry planning begins.
    """

    if bool(config.eval_results_path) == bool(config.raw_score_lists_path):
        raise ValueError("provide exactly one of eval_results_path or raw_score_lists_path")

    package_dir = Path(config.package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)

    normalized_path = Path(config.eval_results_path) if config.eval_results_path else _normalized_path(config)
    normalized_summary: dict[str, Any] | None = None
    if config.raw_score_lists_path:
        if not config.benchmark_data_path:
            raise ValueError("benchmark_data_path is required when raw_score_lists_path is provided")
        normalized_summary = normalize_returned_geneval2_scores(
            raw_score_lists_path=config.raw_score_lists_path,
            benchmark_data_path=config.benchmark_data_path,
            output_path=normalized_path,
            aggregate_by=config.aggregate_by,
            atom_threshold=config.atom_threshold,
        )

    package_build = build_generation_packages_from_manifest(
        manifest_path=config.manifest_path,
        output_dir=package_dir,
        initial_plan_dir=config.initial_plan_dir,
        eval_results_path=normalized_path,
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

    preflight_output = Path(config.preflight_output_path) if config.preflight_output_path else package_dir / "retry_input_preflight.json"
    preflight = check_geneval2_retry_inputs(
        package_manifest_path=package_build.package_manifest_path,
        diagnostic_jobs_path=config.diagnostic_jobs_path,
        eval_results_path=normalized_path,
        expected_count=config.limit,
        output_path=preflight_output,
    )
    status = "ready_for_teacher" if not preflight["critical_count"] and not package_build.missing_eval_report_count else "error"
    errors: list[str] = []
    if package_build.missing_eval_report_count:
        errors.append(f"missing normalized eval report for {package_build.missing_eval_report_count} package(s)")
    if preflight["critical_count"]:
        errors.append("retry input preflight failed")

    summary = {
        "schema_version": "v1",
        "status": status,
        "manifest_path": str(config.manifest_path),
        "diagnostic_jobs_path": str(config.diagnostic_jobs_path),
        "benchmark_data_path": str(config.benchmark_data_path or ""),
        "raw_score_lists_path": str(config.raw_score_lists_path or ""),
        "normalized_reports_path": str(normalized_path),
        "package_dir": str(package_dir),
        "package_manifest_path": package_build.package_manifest_path,
        "preflight_report_path": str(preflight_output),
        "aggregate_by": config.aggregate_by,
        "candidate_index": config.candidate_index,
        "limit": config.limit,
        "teacher_uses_image_bytes": False,
        "normalized_summary": normalized_summary,
        "package_build": package_build.to_dict(),
        "preflight": {key: value for key, value in preflight.items() if key != "issues"},
        "errors": errors,
    }
    summary_path = Path(config.summary_path) if config.summary_path else package_dir / "prepare_summary.json"
    summary["summary_path"] = str(summary_path)
    write_json(summary_path, summary)
    return summary


def normalize_returned_geneval2_scores(
    *,
    raw_score_lists_path: str | Path,
    benchmark_data_path: str | Path,
    output_path: str | Path,
    aggregate_by: str = "candidate_id",
    atom_threshold: float = 0.9,
) -> dict[str, Any]:
    rows = load_geneval2_score_rows(raw_score_lists_path, benchmark_data=benchmark_data_path)
    reports = normalize_geneval2_score_list(
        rows,
        aggregate_by=aggregate_by,
        atom_threshold=atom_threshold,
    )
    output_rows: list[dict[str, Any]] = []
    for group_id, report in sorted(reports.items()):
        raw_rows = report.raw_report.get("rows", []) if isinstance(report.raw_report, dict) else []
        first = raw_rows[0] if raw_rows and isinstance(raw_rows[0], dict) else {}
        output_rows.append(
            {
                "group_id": group_id,
                "candidate_id": first.get("candidate_id") or (group_id if aggregate_by == "candidate_id" else ""),
                "prompt_id": first.get("prompt_id", ""),
                "prompt": first.get("prompt", ""),
                "image_id": first.get("image_id", first.get("image_path", "")),
                "image_path": first.get("image_path", ""),
                "source_index": first.get("source_index"),
                "candidate_index": first.get("candidate_index"),
                "raw_rows_count": len(raw_rows),
                "normalized_report": report.to_dict(),
            }
        )
    written = write_jsonl(output_path, output_rows)
    return {
        "raw_score_lists_path": str(raw_score_lists_path),
        "benchmark_data_path": str(benchmark_data_path),
        "normalized_reports_path": str(output_path),
        "atom_rows": len(rows),
        "report_count": written,
        "aggregate_by": aggregate_by,
        "atom_threshold": atom_threshold,
    }


def _normalized_path(config: Geneval2RetryPrepareConfig) -> Path:
    if config.normalized_output_path:
        return Path(config.normalized_output_path)
    raw_path = Path(str(config.raw_score_lists_path))
    return raw_path.parent / "normalized_reports.jsonl"
