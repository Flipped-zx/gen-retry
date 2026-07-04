"""Semantic quality checks for retry_replan teacher actions."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from gen_retry.schemas.actions import RetryReplanAction
from gen_retry.schemas.reports import NormalizedEvalReport
from gen_retry.skills.skill_library import skill_for_failure_type


@dataclass(frozen=True)
class RetryActionQualityIssue:
    severity: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


def check_retry_action_against_state(
    action: RetryReplanAction,
    state: dict[str, Any],
) -> list[RetryActionQualityIssue]:
    """Check whether a valid retry action covers the current diagnostic state."""

    issues: list[RetryActionQualityIssue] = []
    report = _report_from_state(state)
    if report is None:
        return [
            RetryActionQualityIssue(
                "critical",
                "missing_eval_report",
                "state lacks a parseable normalized eval report",
            )
        ]
    failed = report.failed_constraints
    passed = report.passed_constraints
    if not failed:
        return issues

    failure_types = {item.type for item in failed if item.type}
    action_failure_types = set(action.failure_types)
    missing_failure_types = sorted(failure_types - action_failure_types)
    if missing_failure_types:
        issues.append(
            RetryActionQualityIssue(
                "critical",
                "missing_failure_types",
                f"failure_types must include current failed types: {missing_failure_types}",
            )
        )

    if not action.repair_constraints:
        issues.append(
            RetryActionQualityIssue(
                "critical",
                "missing_repair_constraints",
                "repair_constraints must describe how to fix failed constraints",
            )
        )
    if passed and not action.preserve_constraints:
        issues.append(
            RetryActionQualityIssue(
                "critical",
                "missing_preserve_constraints",
                "preserve_constraints must carry forward constraints that already passed",
            )
        )

    selected_skills = set(_strings(action.skill_revision.get("previous_skills"))) | set(
        _strings(action.skill_revision.get("new_skills"))
    )
    for failure_type in sorted(failure_types):
        expected_skill = skill_for_failure_type(failure_type)
        if expected_skill and expected_skill not in selected_skills:
            issues.append(
                RetryActionQualityIssue(
                    "critical",
                    "missing_repair_skill",
                    f"failure type {failure_type!r} should route to skill {expected_skill!r}",
                )
            )

    repair_text = _joined(
        action.repair_constraints,
        [action.retry_prompt, action.regeneration_strategy, action.diagnosis],
    )
    for constraint in failed:
        target = str(constraint.target).strip()
        if target and _token(target) not in _token(repair_text):
            issues.append(
                RetryActionQualityIssue(
                    "warning",
                    "repair_target_not_mentioned",
                    f"failed target {target!r} is not mentioned in repair text or retry_prompt",
                )
            )
        expected = constraint.expected
        if expected not in (None, "") and _simple_expected(expected) not in _token(repair_text):
            issues.append(
                RetryActionQualityIssue(
                    "warning",
                    "repair_expected_not_mentioned",
                    f"expected value {expected!r} is not mentioned in repair text or retry_prompt",
                )
            )
    return issues


def critical_retry_action_issues(
    action: RetryReplanAction,
    state: dict[str, Any],
) -> list[RetryActionQualityIssue]:
    return [issue for issue in check_retry_action_against_state(action, state) if issue.severity == "critical"]


def format_retry_action_quality_feedback(issues: list[RetryActionQualityIssue]) -> str:
    if not issues:
        return ""
    lines = ["The previous JSON was schema-valid but failed retry-plan quality checks:"]
    for issue in issues:
        lines.append(f"- {issue.code}: {issue.message}")
    lines.append(
        "Return one corrected retry_replan JSON object. Keep the same schema, cover every failed constraint, "
        "preserve passed constraints, and route failures to the required skills."
    )
    return "\n".join(lines)


def _report_from_state(state: dict[str, Any]) -> NormalizedEvalReport | None:
    for key in ("normalized_eval_report", "current_eval_report"):
        value = state.get(key)
        if isinstance(value, dict):
            try:
                return NormalizedEvalReport.from_dict(value)
            except Exception:  # noqa: BLE001
                continue
    return None


def _joined(values: list[str], extras: list[str]) -> str:
    return " ".join([str(item) for item in values + extras if str(item).strip()]).lower()


def _simple_expected(value: Any) -> str:
    if isinstance(value, (int, float)):
        return str(int(value) if int(value) == value else value)
    if isinstance(value, str):
        return _token(value)
    return _token(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
