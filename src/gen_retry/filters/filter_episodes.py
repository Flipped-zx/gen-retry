"""Pass condition and transition classification helpers."""

from __future__ import annotations

from gen_retry.schemas.episode_schema import NormalizedGenevalReport


CRITICAL_FAILURE_TYPES = {
    "missing_object",
    "count_mismatch",
    "color_mismatch",
    "spatial_mismatch",
    "extra_object",
}


def is_passed(report: NormalizedGenevalReport, pass_threshold: float = 0.95) -> bool:
    if not report.failed_constraints:
        return True
    if report.score >= pass_threshold and not _critical_failures(report):
        return True
    return False


def classify_transition(
    before_report: NormalizedGenevalReport,
    after_report: NormalizedGenevalReport,
    pass_threshold: float = 0.95,
) -> str:
    if is_passed(after_report, pass_threshold=pass_threshold):
        return "passed_after_retry"
    before_failed = len(before_report.failed_constraints)
    after_failed = len(after_report.failed_constraints)
    new_critical = _critical_types(after_report) - _critical_types(before_report)
    if after_failed < before_failed and not new_critical:
        return "partial_improved"
    if after_report.score > before_report.score and not new_critical:
        return "partial_improved"
    if after_failed > before_failed or new_critical:
        return "regressed"
    return "no_improvement"


def has_new_critical_failure(
    before_report: NormalizedGenevalReport,
    after_report: NormalizedGenevalReport,
) -> bool:
    return bool(_critical_types(after_report) - _critical_types(before_report))


def _critical_failures(report: NormalizedGenevalReport) -> list[str]:
    return [item.type for item in report.failed_constraints if item.type in CRITICAL_FAILURE_TYPES]


def _critical_types(report: NormalizedGenevalReport) -> set[str]:
    return {item.type for item in report.failed_constraints if item.type in CRITICAL_FAILURE_TYPES}

