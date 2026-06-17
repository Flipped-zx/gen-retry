"""Normalize Geneval-style diagnostics into retry targets."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


CHECK_TO_FAILURE_TYPE = {
    "object_presence": "missing_object",
    "counting": "count_mismatch",
    "color_binding": "color_mismatch",
    "colors": "color_mismatch",
    "position": "spatial_mismatch",
    "spatial_relation": "spatial_mismatch",
}

FAILURE_TO_SKILL = {
    "missing_object": "object_presence",
    "count_mismatch": "quantity_counting",
    "color_mismatch": "attribute_binding",
    "spatial_mismatch": "spatial_layout",
    "unverifiable_constraint": "visibility_and_anti_occlusion",
}


def _detected_counts(detected: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(item.get("label", "")).strip() for item in detected if item.get("label"))


def _detected_colors(detected: list[dict[str, Any]]) -> dict[str, Counter[str]]:
    colors: dict[str, Counter[str]] = defaultdict(Counter)
    for item in detected:
        label = str(item.get("label", "")).strip()
        color = str(item.get("color", "")).strip()
        if label and color:
            colors[label][color] += 1
    return colors


def _constraint(kind: str, target: str, status: str, **extra: Any) -> dict[str, Any]:
    out = {"type": kind, "target": target, "status": status}
    out.update(extra)
    return out


def normalize_geneval_diagnostic(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a Geneval-like diagnostic object into preserve and repair fields."""

    expected = raw.get("expected") or {}
    detected = raw.get("detected") or []
    checks = raw.get("checks") or {}

    objects = list(expected.get("objects") or [])
    expected_counts = expected.get("count") or {}
    expected_colors = expected.get("color") or {}
    counts = _detected_counts(detected if isinstance(detected, list) else [])
    colors = _detected_colors(detected if isinstance(detected, list) else [])

    passed_constraints: list[dict[str, Any]] = []
    failed_constraints: list[dict[str, Any]] = []
    failure_types: list[str] = []
    preserve_candidates: list[dict[str, Any]] = []
    repair_targets: list[dict[str, Any]] = []

    if checks.get("object_presence") is True:
        for obj in objects:
            passed_constraints.append(_constraint("object_presence", str(obj), "passed"))
            preserve_candidates.append({"target": str(obj), "property": "presence", "value": True})
    elif checks.get("object_presence") is False:
        failure_types.append("missing_object")
        for obj in objects:
            found = counts.get(str(obj), 0)
            if found <= 0:
                failed_constraints.append(
                    _constraint("object_presence", str(obj), "failed", expected=True, detected=False)
                )

    if checks.get("counting") is True:
        for obj, expected_count in expected_counts.items():
            passed_constraints.append(
                _constraint(
                    "counting",
                    str(obj),
                    "passed",
                    expected=expected_count,
                    detected=counts.get(str(obj), 0),
                )
            )
    elif checks.get("counting") is False:
        failure_types.append("count_mismatch")
        for obj, expected_count in expected_counts.items():
            detected_count = counts.get(str(obj), 0)
            if detected_count != expected_count:
                failed_constraints.append(
                    _constraint(
                        "counting",
                        str(obj),
                        "failed",
                        expected=expected_count,
                        detected=detected_count,
                    )
                )

    if checks.get("color_binding") is True or checks.get("colors") is True:
        for obj, expected_color in expected_colors.items():
            passed_constraints.append(
                _constraint("color_binding", str(obj), "passed", expected=expected_color)
            )
            preserve_candidates.append(
                {"target": str(obj), "property": "color", "value": expected_color}
            )
    elif checks.get("color_binding") is False or checks.get("colors") is False:
        failure_types.append("color_mismatch")
        for obj, expected_color in expected_colors.items():
            color_counts = colors.get(str(obj), Counter())
            detected_color_count = color_counts.get(str(expected_color), 0)
            target_count = int(expected_counts.get(obj, 1) or 1)
            if detected_color_count < target_count:
                failed_constraints.append(
                    _constraint(
                        "color_binding",
                        str(obj),
                        "failed",
                        expected=expected_color,
                        detected=dict(color_counts),
                    )
                )

    for check_name, passed in checks.items():
        if passed is False:
            failure_type = CHECK_TO_FAILURE_TYPE.get(check_name, f"{check_name}_failed")
            if failure_type not in failure_types:
                failure_types.append(failure_type)
        elif passed is True and check_name not in {"object_presence", "counting", "color_binding", "colors"}:
            passed_constraints.append(_constraint(check_name, "diagnostic", "passed"))

    if not failure_types and raw.get("failure_reason"):
        failure_types.append("unverifiable_constraint")

    for failed in failed_constraints:
        failure_type = CHECK_TO_FAILURE_TYPE.get(failed["type"], "unverifiable_constraint")
        skill = FAILURE_TO_SKILL.get(failure_type, "preserve_correct_constraints")
        instruction = _repair_instruction(skill, failed)
        repair_targets.append(
            {
                "skill": skill,
                "target": failed.get("target", ""),
                "failure_type": failure_type,
                "instruction": instruction,
            }
        )

    return {
        "prompt": raw.get("prompt", ""),
        "category": raw.get("category", ""),
        "passed_constraints": passed_constraints,
        "failed_constraints": failed_constraints,
        "failure_types": sorted(set(failure_types)),
        "preserve_candidates": _dedupe_dicts(preserve_candidates),
        "repair_targets": repair_targets,
        "failure_reason": raw.get("failure_reason", ""),
    }


def _repair_instruction(skill: str, failed: dict[str, Any]) -> str:
    target = str(failed.get("target", "target"))
    if skill == "quantity_counting":
        expected = failed.get("expected")
        return f"Render exactly {expected} separate visible {target} instances."
    if skill == "attribute_binding":
        expected = failed.get("expected")
        return f"Bind {target} to the expected attribute {expected!r} without leakage."
    if skill == "object_presence":
        return f"Make the required {target} clearly visible."
    if skill == "spatial_layout":
        return f"Repair the spatial relation involving {target}."
    return f"Repair the failed constraint for {target}."


def _dedupe_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[tuple[str, str], ...]] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = tuple(sorted((str(k), repr(v)) for k, v in item.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
