"""Normalize real Geneval outputs into teacher-ready retry diagnostics."""

from __future__ import annotations

from collections import Counter
from typing import Any

from gen_retry.schemas.episode_schema import Constraint, NormalizedGenevalReport


CRITICAL_FAILURE_TYPES = {
    "missing_object",
    "count_mismatch",
    "color_mismatch",
    "spatial_mismatch",
    "extra_object",
}


CHECK_TO_FAILURE_TYPE = {
    "object_presence": "missing_object",
    "counting": "count_mismatch",
    "color_binding": "color_mismatch",
    "colors": "color_mismatch",
    "spatial_relation": "spatial_mismatch",
    "position": "spatial_mismatch",
    "extra_object": "extra_object",
}


def normalize_geneval_output(
    raw: dict[str, Any],
    *,
    prompt: str,
    expected: dict[str, Any] | None = None,
    category: str = "",
) -> tuple[NormalizedGenevalReport, dict[str, Any]]:
    """Return a normalized report and a Geneval-style diagnostic object.

    The parser accepts both already-structured outputs and simpler Geneval-like
    dictionaries containing `checks`, `expected`, `detected`, and
    `failure_reason`.
    """

    expected = dict(expected or raw.get("expected") or {})
    detected = raw.get("detected") if isinstance(raw.get("detected"), list) else []
    checks = raw.get("checks") if isinstance(raw.get("checks"), dict) else {}

    failed = _constraints(raw.get("failed_constraints"), "failed")
    passed = _constraints(raw.get("passed_constraints"), "passed")
    uncertain = _constraints(raw.get("uncertain_constraints"), "uncertain")

    if not failed and checks:
        failed.extend(_failed_from_checks(checks, expected, detected, str(raw.get("failure_reason", ""))))
    if not passed and checks:
        passed.extend(_passed_from_checks(checks, expected, detected))

    score = _score(raw, failed, checks)
    failure_reason = str(raw.get("failure_reason") or _failure_reason(failed)).strip()
    normalized = NormalizedGenevalReport(
        score=score,
        passed_constraints=passed,
        failed_constraints=failed,
        uncertain_constraints=uncertain,
        raw_report=raw,
    )
    diagnostic = {
        "prompt": prompt,
        "category": category or str(raw.get("category", "")),
        "expected": expected,
        "detected": detected,
        "checks": checks or _checks_from_constraints(passed, failed),
        "score": score,
        "passed_constraints": [item.to_dict() for item in passed],
        "failed_constraints": [item.to_dict() for item in failed],
        "uncertain_constraints": [item.to_dict() for item in uncertain],
        "failure_reason": failure_reason,
        "critical_failure_types": sorted(
            {item.type for item in failed if item.type in CRITICAL_FAILURE_TYPES}
        ),
    }
    return normalized, diagnostic


def teacher_diagnostic_row(
    *,
    candidate_id: str,
    sample_id: str,
    candidate_index: int,
    prompt: str,
    image_path: str,
    diagnostic: dict[str, Any],
    generator_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a row consumable by scripts/build_teacher_retry_actions.py later."""

    return {
        "id": candidate_id,
        "sample_id": sample_id,
        "candidate_index": candidate_index,
        "image_path": image_path,
        "first_attempt_prompt": prompt,
        "diagnostic": diagnostic,
        "generator_metadata": generator_metadata or {},
    }


def _constraints(value: Any, status: str) -> list[Constraint]:
    if not isinstance(value, list):
        return []
    out: list[Constraint] = []
    for item in value:
        if isinstance(item, dict):
            data = dict(item)
            data.setdefault("status", status)
            out.append(Constraint.from_dict(data))
    return out


def _failed_from_checks(
    checks: dict[str, Any],
    expected: dict[str, Any],
    detected: list[Any],
    failure_reason: str,
) -> list[Constraint]:
    failed: list[Constraint] = []
    counts = _detected_counts(detected)
    colors = _detected_colors(detected)
    expected_counts = expected.get("count") if isinstance(expected.get("count"), dict) else {}
    expected_colors = expected.get("color") if isinstance(expected.get("color"), dict) else {}

    for check_name, value in checks.items():
        if value is not False:
            continue
        failure_type = CHECK_TO_FAILURE_TYPE.get(str(check_name), f"{check_name}_failed")
        if failure_type == "count_mismatch":
            for target, expected_count in expected_counts.items():
                detected_count = counts.get(str(target), 0)
                if detected_count != expected_count:
                    failed.append(
                        Constraint(
                            type="count_mismatch",
                            target=str(target),
                            expected=expected_count,
                            detected=detected_count,
                            status="failed",
                        )
                    )
        elif failure_type == "color_mismatch":
            for target, expected_color in expected_colors.items():
                color_counts = colors.get(str(target), Counter())
                if color_counts.get(str(expected_color), 0) <= 0:
                    failed.append(
                        Constraint(
                            type="color_mismatch",
                            target=str(target),
                            expected=expected_color,
                            detected=dict(color_counts),
                            status="failed",
                        )
                    )
        elif failure_type == "spatial_mismatch":
            spatial = expected.get("spatial")
            if isinstance(spatial, list) and spatial:
                for item in spatial:
                    if isinstance(item, dict):
                        target = " ".join(
                            str(item.get(key, "")).strip()
                            for key in ("subject", "relation", "object")
                            if str(item.get(key, "")).strip()
                        )
                        failed.append(
                            Constraint(
                                type="spatial_mismatch",
                                target=target or "spatial_relation",
                                expected=item,
                                detected=failure_reason,
                                status="failed",
                            )
                        )
            else:
                failed.append(
                    Constraint(
                        type="spatial_mismatch",
                        target="spatial_relation",
                        expected="expected spatial relation",
                        detected=failure_reason,
                        status="failed",
                    )
                )
        elif failure_type == "missing_object":
            objects = expected.get("objects") if isinstance(expected.get("objects"), list) else []
            for target in objects:
                if counts.get(str(target), 0) <= 0:
                    failed.append(
                        Constraint(
                            type="missing_object",
                            target=str(target),
                            expected="present",
                            detected="missing",
                            status="failed",
                        )
                    )
            if not failed:
                failed.append(
                    Constraint(
                        type="missing_object",
                        target="required_object",
                        expected="present",
                        detected=failure_reason,
                        status="failed",
                    )
                )
        else:
            failed.append(
                Constraint(
                    type=failure_type,
                    target=str(check_name),
                    expected=True,
                    detected=False,
                    status="failed",
                    details={"failure_reason": failure_reason},
                )
            )
    return _dedupe_constraints(failed)


def _passed_from_checks(
    checks: dict[str, Any],
    expected: dict[str, Any],
    detected: list[Any],
) -> list[Constraint]:
    passed: list[Constraint] = []
    counts = _detected_counts(detected)
    for check_name, value in checks.items():
        if value is not True:
            continue
        if check_name == "object_presence":
            for target in expected.get("objects", []) if isinstance(expected.get("objects"), list) else []:
                passed.append(
                    Constraint(
                        type="object_presence",
                        target=str(target),
                        expected="present",
                        detected="present",
                        status="passed",
                    )
                )
        elif check_name == "counting":
            counts_expected = expected.get("count") if isinstance(expected.get("count"), dict) else {}
            for target, expected_count in counts_expected.items():
                passed.append(
                    Constraint(
                        type="count_mismatch",
                        target=str(target),
                        expected=expected_count,
                        detected=counts.get(str(target), expected_count),
                        status="passed",
                    )
                )
        elif check_name in {"color_binding", "colors"}:
            colors_expected = expected.get("color") if isinstance(expected.get("color"), dict) else {}
            for target, expected_color in colors_expected.items():
                passed.append(
                    Constraint(
                        type="color_mismatch",
                        target=str(target),
                        expected=expected_color,
                        detected=expected_color,
                        status="passed",
                    )
                )
        else:
            passed.append(
                Constraint(
                    type=str(check_name),
                    target="diagnostic",
                    expected=True,
                    detected=True,
                    status="passed",
                )
            )
    return _dedupe_constraints(passed)


def _detected_counts(detected: list[Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in detected:
        if isinstance(item, dict) and item.get("label"):
            counts[str(item["label"])] += 1
    return counts


def _detected_colors(detected: list[Any]) -> dict[str, Counter[str]]:
    colors: dict[str, Counter[str]] = {}
    for item in detected:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        color = str(item.get("color", "")).strip()
        if label and color:
            colors.setdefault(label, Counter())[color] += 1
    return colors


def _score(raw: dict[str, Any], failed: list[Constraint], checks: dict[str, Any]) -> float:
    value = raw.get("score")
    if isinstance(value, int | float):
        return max(0.0, min(1.0, float(value)))
    if checks:
        total = len(checks)
        passed = sum(1 for item in checks.values() if item is True)
        return passed / total if total else 0.0
    return 1.0 if not failed else 0.0


def _failure_reason(failed: list[Constraint]) -> str:
    if not failed:
        return ""
    parts = []
    for item in failed:
        parts.append(
            f"{item.type} on {item.target}: expected {item.expected}, detected {item.detected}"
        )
    return "; ".join(parts)


def _checks_from_constraints(
    passed: list[Constraint],
    failed: list[Constraint],
) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    for item in passed:
        checks[_check_name(item.type)] = True
    for item in failed:
        checks[_check_name(item.type)] = False
    return checks


def _check_name(failure_type: str) -> str:
    return {
        "missing_object": "object_presence",
        "count_mismatch": "counting",
        "color_mismatch": "color_binding",
        "spatial_mismatch": "spatial_relation",
        "extra_object": "extra_object",
    }.get(failure_type, failure_type)


def _dedupe_constraints(items: list[Constraint]) -> list[Constraint]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[Constraint] = []
    for item in items:
        key = (item.type, item.target, repr(item.expected), repr(item.detected))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
