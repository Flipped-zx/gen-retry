"""Preflight checks for GenEval2 diagnostics before teacher retry planning."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gen_retry.schemas.actions import InitialPlanAction
from gen_retry.schemas.reports import NormalizedEvalReport
from gen_retry.utils.io import read_json, read_jsonl, write_json


@dataclass(frozen=True)
class RetryInputIssue:
    severity: str
    code: str
    message: str
    candidate_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "candidate_id": self.candidate_id,
        }


def check_geneval2_retry_inputs(
    *,
    package_manifest_path: str | Path,
    diagnostic_jobs_path: str | Path | None = None,
    eval_results_path: str | Path | None = None,
    expected_count: int | None = 100,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    issues: list[RetryInputIssue] = []
    packages = _read_package_manifest(package_manifest_path, issues)
    jobs = _read_jobs(diagnostic_jobs_path, issues) if diagnostic_jobs_path else {}
    reports = _read_reports(eval_results_path, issues) if eval_results_path else {}
    has_diagnostic_jobs = diagnostic_jobs_path is not None
    has_eval_results = eval_results_path is not None

    if expected_count is not None and len(packages) != expected_count:
        issues.append(
            RetryInputIssue(
                "critical",
                "package_count_mismatch",
                f"package manifest has {len(packages)} rows, expected {expected_count}",
            )
        )
    if has_diagnostic_jobs and expected_count is not None and len(jobs) != expected_count:
        issues.append(
            RetryInputIssue(
                "critical",
                "diagnostic_job_count_mismatch",
                f"diagnostic jobs have {len(jobs)} rows, expected {expected_count}",
            )
        )
    if has_eval_results and expected_count is not None and len(reports) != expected_count:
        issues.append(
            RetryInputIssue(
                "critical",
                "eval_report_count_mismatch",
                f"eval reports have {len(reports)} rows, expected {expected_count}",
            )
        )

    package_ids = set(packages)
    job_ids = set(jobs)
    report_ids = set(reports)
    if has_diagnostic_jobs:
        _missing_extra_issues(
            issues,
            left=package_ids,
            right=job_ids,
            left_name="package",
            right_name="diagnostic_job",
        )
    if has_eval_results:
        _missing_extra_issues(
            issues,
            left=package_ids,
            right=report_ids,
            left_name="package",
            right_name="eval_report",
        )

    for candidate_id, row in packages.items():
        package_path = row.get("package_path")
        if not package_path:
            issues.append(RetryInputIssue("critical", "missing_package_path", "package row lacks package_path", candidate_id))
            continue
        try:
            package = read_json(package_path)
        except Exception as exc:  # noqa: BLE001
            issues.append(RetryInputIssue("critical", "unreadable_package", str(exc), candidate_id))
            continue
        if not isinstance(package.get("previous_initial_plan"), dict) or not package.get("previous_initial_plan"):
            issues.append(
                RetryInputIssue(
                    "critical",
                    "missing_initial_plan",
                    "package lacks previous_initial_plan",
                    candidate_id,
                )
            )
        else:
            try:
                InitialPlanAction.from_dict(dict(package.get("previous_initial_plan") or {}))
            except Exception as exc:  # noqa: BLE001
                issues.append(RetryInputIssue("critical", "invalid_initial_plan", str(exc), candidate_id))
        metadata = package.get("metadata") if isinstance(package.get("metadata"), dict) else {}
        if metadata.get("teacher_uses_image_bytes") is not False:
            issues.append(
                RetryInputIssue(
                    "critical",
                    "teacher_image_boundary_unclear",
                    "package metadata must declare teacher_uses_image_bytes=false",
                    candidate_id,
                )
            )

    report_summaries = [_report_summary(candidate_id, report) for candidate_id, report in reports.items()]
    pass_count = sum(1 for item in report_summaries if not item["failed_constraints"])
    retry_count = len(report_summaries) - pass_count
    failure_type_counts: Counter[str] = Counter()
    score_values: list[float] = []
    for item in report_summaries:
        score_values.append(float(item["score"]))
        failure_type_counts.update(item["failure_types"])

    critical_count = sum(1 for issue in issues if issue.severity == "critical")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    report = {
        "status": "fail" if critical_count else "warning" if warning_count else "pass",
        "package_manifest_path": str(package_manifest_path),
        "diagnostic_jobs_path": str(diagnostic_jobs_path or ""),
        "eval_results_path": str(eval_results_path or ""),
        "expected_count": expected_count,
        "package_count": len(packages),
        "diagnostic_job_count": len(jobs) if has_diagnostic_jobs else None,
        "eval_report_count": len(reports) if has_eval_results else None,
        "pass_count": pass_count if has_eval_results else None,
        "retry_candidate_count": retry_count if has_eval_results else None,
        "score_min": min(score_values) if score_values else None,
        "score_max": max(score_values) if score_values else None,
        "score_mean": sum(score_values) / len(score_values) if score_values else None,
        "failure_type_counts": dict(sorted(failure_type_counts.items())),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "issues": [issue.to_dict() for issue in issues],
        "sample_report_summaries": report_summaries[:5],
    }
    if output_path:
        write_json(output_path, report)
    return report


def _read_package_manifest(path: str | Path, issues: list[RetryInputIssue]) -> dict[str, dict[str, Any]]:
    rows = read_jsonl(path)
    return _index_rows(rows, key="candidate_id", source="package_manifest", issues=issues)


def _read_jobs(path: str | Path | None, issues: list[RetryInputIssue]) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    rows = read_jsonl(path)
    return _index_rows(rows, key="candidate_id", source="diagnostic_jobs", issues=issues)


def _read_reports(path: str | Path | None, issues: list[RetryInputIssue]) -> dict[str, NormalizedEvalReport]:
    if not path:
        return {}
    rows = read_jsonl(path)
    indexed: dict[str, NormalizedEvalReport] = {}
    seen: set[str] = set()
    for index, row in enumerate(rows):
        candidate_id = str(row.get("candidate_id") or row.get("group_id") or "").strip()
        if not candidate_id:
            issues.append(RetryInputIssue("critical", "missing_eval_candidate_id", f"eval row {index} lacks candidate_id"))
            continue
        if candidate_id in seen:
            issues.append(RetryInputIssue("critical", "duplicate_eval_candidate_id", "duplicate eval report", candidate_id))
            continue
        seen.add(candidate_id)
        report_data = row.get("normalized_report") if isinstance(row.get("normalized_report"), dict) else row
        try:
            indexed[candidate_id] = NormalizedEvalReport.from_dict(dict(report_data))
        except Exception as exc:  # noqa: BLE001
            issues.append(RetryInputIssue("critical", "invalid_eval_report", str(exc), candidate_id))
    return indexed


def _index_rows(
    rows: list[dict[str, Any]],
    *,
    key: str,
    source: str,
    issues: list[RetryInputIssue],
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        candidate_id = str(row.get(key, "")).strip()
        if not candidate_id:
            issues.append(RetryInputIssue("critical", f"missing_{source}_candidate_id", f"row {index} lacks {key}"))
            continue
        if candidate_id in indexed:
            issues.append(RetryInputIssue("critical", f"duplicate_{source}_candidate_id", "duplicate candidate_id", candidate_id))
            continue
        indexed[candidate_id] = row
    return indexed


def _missing_extra_issues(
    issues: list[RetryInputIssue],
    *,
    left: set[str],
    right: set[str],
    left_name: str,
    right_name: str,
) -> None:
    missing = sorted(left - right)
    extra = sorted(right - left)
    for candidate_id in missing[:20]:
        issues.append(
            RetryInputIssue(
                "critical",
                f"{right_name}_missing_for_{left_name}",
                f"{right_name} is missing for {left_name} candidate",
                candidate_id,
            )
        )
    for candidate_id in extra[:20]:
        issues.append(
            RetryInputIssue(
                "critical",
                f"{right_name}_extra",
                f"{right_name} has no matching {left_name} candidate",
                candidate_id,
            )
        )


def _report_summary(candidate_id: str, report: NormalizedEvalReport) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "score": report.score,
        "passed_constraints": len(report.passed_constraints),
        "failed_constraints": len(report.failed_constraints),
        "uncertain_constraints": len(report.uncertain_constraints),
        "failure_types": sorted({item.type for item in report.failed_constraints if item.type}),
    }
