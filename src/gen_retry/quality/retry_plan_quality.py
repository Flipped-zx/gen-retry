"""Heuristic quality checks for teacher retry-plan packages."""

from __future__ import annotations

from dataclasses import dataclass
import glob
import json
import re
from pathlib import Path
from typing import Any

from gen_retry.schemas.actions import DIRECT_EDIT_KEYS, ActionValidationError, RetryReplanAction
from gen_retry.schemas.reports import NormalizedEvalReport
from gen_retry.utils.io import read_json, read_jsonl


FAILURE_SKILL_ROUTING = {
    "count_mismatch": "quantity_counting",
    "missing_object": "object_presence",
    "extra_object": "negative_constraints",
    "forbidden_object_present": "negative_constraints",
    "color_mismatch": "attribute_binding",
    "attribute_mismatch": "attribute_binding",
    "spatial_mismatch": "spatial_layout",
    "relation_mismatch": "spatial_layout",
    "action_mismatch": "spatial_layout",
    "occluded_object": "anti_occlusion",
    "low_visibility": "clarity_visibility",
}

FORBIDDEN_IMAGE_INPUT_KEYS = {
    "b64_json",
    "base64",
    "image_base64",
    "image_bytes",
    "image_data",
    "image_url",
    "input_image",
}

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(r"(?i)\bapi[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9._-]{16,}"),
)


@dataclass(frozen=True)
class RetryPlanQualityIssue:
    severity: str
    code: str
    message: str
    package_path: str = ""
    candidate_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "package_path": self.package_path,
            "candidate_id": self.candidate_id,
        }


def load_retry_plan_packages(paths: list[str | Path]) -> list[tuple[str, dict[str, Any]]]:
    packages: list[tuple[str, dict[str, Any]]] = []
    for path in _expand_inputs(paths):
        if path.name.endswith(".jsonl"):
            for row in read_jsonl(path):
                output_path = row.get("output_path")
                if output_path:
                    source = Path(str(output_path))
                    packages.append((str(source), read_json(source)))
                else:
                    packages.append((str(path), row))
        else:
            packages.append((str(path), read_json(path)))
    return packages


def check_retry_plan_packages(packages: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    issues: list[RetryPlanQualityIssue] = []
    checked = 0
    retry_actions = 0
    stopped = 0
    for package_path, package in packages:
        checked += 1
        package_issues = check_retry_plan_package(package, package_path=package_path)
        issues.extend(package_issues)
        stop = package.get("stop") if isinstance(package.get("stop"), dict) else {}
        if stop.get("should_stop") is True:
            stopped += 1
        if isinstance(package.get("teacher_action"), dict):
            retry_actions += 1
    critical = sum(1 for issue in issues if issue.severity == "critical")
    warnings = sum(1 for issue in issues if issue.severity == "warning")
    return {
        "status": "fail" if critical else "warning" if warnings else "pass",
        "packages_checked": checked,
        "retry_actions_checked": retry_actions,
        "stopped_without_retry": stopped,
        "critical_count": critical,
        "warning_count": warnings,
        "issues": [issue.to_dict() for issue in issues],
    }


def check_retry_plan_package(
    package: dict[str, Any],
    *,
    package_path: str = "",
) -> list[RetryPlanQualityIssue]:
    issues: list[RetryPlanQualityIssue] = []
    candidate_id = str(package.get("candidate_id", ""))

    def critical(code: str, message: str) -> None:
        issues.append(
            RetryPlanQualityIssue(
                "critical",
                code,
                message,
                package_path=package_path,
                candidate_id=candidate_id,
            )
        )

    def warning(code: str, message: str) -> None:
        issues.append(
            RetryPlanQualityIssue(
                "warning",
                code,
                message,
                package_path=package_path,
                candidate_id=candidate_id,
            )
        )

    stop = package.get("stop") if isinstance(package.get("stop"), dict) else {}
    if stop.get("should_stop") is True:
        if package.get("teacher_action") is not None:
            critical("stopped_has_teacher_action", "stopped package should not include a teacher_action")
        return issues

    request = package.get("teacher_request")
    action_payload = package.get("teacher_action")
    if not isinstance(request, dict):
        critical("missing_teacher_request", "retry package must persist teacher_request")
        request = {}
    if not isinstance(action_payload, dict):
        critical("missing_teacher_action", "retry package must include teacher_action when stop.should_stop is false")
        return issues

    try:
        action = RetryReplanAction.from_dict(action_payload)
    except (ActionValidationError, ValueError) as exc:
        critical("invalid_teacher_action_schema", f"teacher_action violates RetryReplanAction schema: {exc}")
        return issues

    report = _current_report(request, package)
    failed = report.failed_constraints if report else []
    passed = report.passed_constraints if report else []
    if report is None:
        critical("missing_eval_report", "teacher_request/package lacks a parseable normalized eval report")
    elif not failed:
        warning("retry_without_failed_constraints", "retry action exists but current report has no failed constraints")

    failure_types = {item.type for item in failed if item.type}
    action_failure_types = set(action.failure_types)
    missing_failure_types = sorted(failure_types - action_failure_types)
    if missing_failure_types:
        critical(
            "missing_failure_types",
            f"teacher_action.failure_types omits failed report types: {missing_failure_types}",
        )

    repair_text = _joined(
        action.repair_constraints,
        [action.retry_prompt, action.regeneration_strategy, action.diagnosis],
    )
    preserve_text = _joined(action.preserve_constraints, [action.retry_prompt])
    for constraint in failed:
        target = str(constraint.target).strip()
        if target and _token(target) not in _token(repair_text):
            warning(
                "repair_target_not_mentioned",
                f"failed target {target!r} is not mentioned in repair constraints or retry prompt",
            )
        expected = constraint.expected
        if expected not in (None, "") and _simple_expected(expected) not in _token(repair_text):
            warning(
                "repair_expected_not_mentioned",
                f"failed expected value {expected!r} is not mentioned in repair constraints or retry prompt",
            )

    if passed and not action.preserve_constraints:
        critical("missing_preserve_constraints", "passed constraints exist but preserve_constraints is empty")
    for constraint in passed:
        target = str(constraint.target).strip()
        if target and _token(target) not in _token(preserve_text):
            warning(
                "preserve_target_not_mentioned",
                f"passed target {target!r} is not mentioned in preserve constraints or retry prompt",
            )

    new_skills = set(_strings(action.skill_revision.get("new_skills")))
    previous_skills = set(_strings(action.skill_revision.get("previous_skills")))
    selected_skills = new_skills | previous_skills
    for failure_type in failure_types:
        expected_skill = FAILURE_SKILL_ROUTING.get(failure_type)
        if expected_skill and expected_skill not in selected_skills:
            critical(
                "missing_repair_skill",
                f"failure type {failure_type!r} should route to {expected_skill!r}, got {sorted(selected_skills)}",
            )

    direct_keys = sorted(DIRECT_EDIT_KEYS & _deep_keys(action_payload))
    if direct_keys:
        critical("direct_image_edit_key", f"teacher_action contains direct image edit keys: {direct_keys}")
    forbidden_input_keys = sorted(FORBIDDEN_IMAGE_INPUT_KEYS & _deep_keys(request))
    if forbidden_input_keys:
        critical("raw_image_input_key", f"teacher_request contains raw image upload keys: {forbidden_input_keys}")
    if _contains_secret(package):
        critical("secret_like_string", "package contains a string that looks like an API key or bearer token")

    memory = request.get("memory") if isinstance(request.get("memory"), dict) else {}
    regressed = memory.get("regressed_constraints") or request.get("regressed_constraints") or []
    score_delta = _float(memory.get("score_delta_from_previous", request.get("score_delta_from_previous", 0.0)))
    if (regressed or score_delta < 0) and action.branch_source == "latest":
        warning(
            "regression_branches_from_latest",
            "current attempt regressed but teacher_action.branch_source is latest, not best_so_far",
        )

    return issues


def _expand_inputs(paths: list[str | Path]) -> list[Path]:
    expanded: list[Path] = []
    for value in paths:
        text = str(value)
        matches = sorted(glob.glob(text)) if any(ch in text for ch in "*?[]") else []
        if matches:
            expanded.extend(Path(match) for match in matches)
        else:
            expanded.append(Path(text))
    return expanded


def _current_report(request: dict[str, Any], package: dict[str, Any]) -> NormalizedEvalReport | None:
    for value in (
        request.get("current_eval_report"),
        request.get("normalized_eval_report"),
        package.get("evaluation"),
    ):
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


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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


def _contains_secret(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)
