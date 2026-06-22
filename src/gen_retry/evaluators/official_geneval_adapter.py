"""Adapters for the official GenEval ``evaluate_images.py`` output."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from gen_retry.evaluators.geneval_result_normalizer import (
    normalize_geneval_output,
    teacher_diagnostic_row,
)


GENEVAL_COLORS = {
    "red",
    "orange",
    "yellow",
    "green",
    "blue",
    "purple",
    "pink",
    "brown",
    "black",
    "white",
}


def official_result_to_candidate_row(
    row: dict[str, Any],
    *,
    index: int = 0,
    generator_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert one official GenEval result row into gen-retry diagnostics."""

    metadata = parse_json_object(row.get("metadata")) or {}
    raw_report = official_result_to_raw_report(row)
    sample_id, candidate_id, candidate_index = candidate_identity(row, metadata, index=index)
    prompt = str(row.get("prompt") or metadata.get("prompt") or "").strip()
    category = str(row.get("tag") or metadata.get("tag") or "")
    normalized, diagnostic = normalize_geneval_output(
        raw_report,
        prompt=prompt,
        expected=raw_report.get("expected") if isinstance(raw_report.get("expected"), dict) else {},
        category=category,
    )
    image_path = str(row.get("filename") or row.get("image_path") or "")
    gen_meta = dict(generator_metadata or {})
    candidate = {
        "id": candidate_id,
        "sample_id": sample_id,
        "candidate_id": candidate_id,
        "candidate_index": candidate_index,
        "prompt": prompt,
        "category": category,
        "image_path": image_path,
        "generator_metadata": gen_meta,
        "geneval_report": normalized.to_dict(),
        "diagnostic": diagnostic,
        "official_geneval": row,
    }
    candidate["teacher_row"] = teacher_diagnostic_row(
        candidate_id=candidate_id,
        sample_id=sample_id,
        candidate_index=candidate_index,
        prompt=prompt,
        image_path=image_path,
        diagnostic=diagnostic,
        generator_metadata=gen_meta,
    )
    return candidate


def official_result_to_raw_report(row: dict[str, Any]) -> dict[str, Any]:
    """Build a structured report from the official GenEval per-image row."""

    metadata = parse_json_object(row.get("metadata")) or {}
    details = parse_json_object(row.get("details")) or {}
    expected = geneval_metadata_to_expected(metadata)
    detected = geneval_details_to_detected(details)
    correct = as_bool(row.get("correct"))
    failure_reason = str(row.get("reason") or "").strip()
    return {
        "score": 1.0 if correct else 0.0,
        "expected": expected,
        "detected": detected,
        "checks": infer_checks(
            metadata=metadata,
            expected=expected,
            detected=detected,
            correct=correct,
            failure_reason=failure_reason,
        ),
        "failure_reason": "" if correct else failure_reason,
        "category": str(row.get("tag") or metadata.get("tag") or ""),
        "official_geneval": row,
    }


def geneval_metadata_to_expected(metadata: dict[str, Any]) -> dict[str, Any]:
    """Convert official GenEval metadata clauses into gen-retry expected fields."""

    expected: dict[str, Any] = {"objects": [], "count": {}}
    colors: dict[str, Any] = {}
    spatial: list[dict[str, str]] = []
    include = metadata.get("include") if isinstance(metadata.get("include"), list) else []
    exclude = metadata.get("exclude") if isinstance(metadata.get("exclude"), list) else []

    include_classes: list[str] = []
    for req in include:
        if not isinstance(req, dict):
            continue
        classname = str(req.get("class", "")).strip()
        if not classname:
            continue
        include_classes.append(classname)
        if classname not in expected["objects"]:
            expected["objects"].append(classname)
        count = _safe_int(req.get("count"), 1)
        expected["count"][classname] = max(count, int(expected["count"].get(classname, 0)))
        if req.get("color") is not None:
            colors[classname] = str(req.get("color")).strip()
        if isinstance(req.get("position"), list) and len(req["position"]) >= 2:
            relation = str(req["position"][0]).strip()
            target_index = _safe_int(req["position"][1], -1)
            target = include_classes[target_index] if 0 <= target_index < len(include_classes) else "target"
            spatial.append(
                {
                    "subject": classname,
                    "relation": relation.replace(" ", "_"),
                    "object": target,
                }
            )

    if colors:
        expected["color"] = colors
    if spatial:
        expected["spatial"] = spatial
    if exclude:
        expected["exclude"] = [
            {"class": str(req.get("class", "")).strip(), "count": _safe_int(req.get("count"), 1)}
            for req in exclude
            if isinstance(req, dict) and str(req.get("class", "")).strip()
        ]
    return expected


def geneval_details_to_detected(details: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert official GenEval detected box details into flat detected objects."""

    detected: list[dict[str, Any]] = []
    for label, boxes in details.items():
        if not isinstance(boxes, list):
            continue
        for box in boxes:
            item: dict[str, Any] = {"label": str(label)}
            if isinstance(box, list):
                item["bbox"] = box[:4]
                if len(box) >= 5:
                    item["score"] = box[4]
            detected.append(item)
    return detected


def infer_checks(
    *,
    metadata: dict[str, Any],
    expected: dict[str, Any],
    detected: list[dict[str, Any]],
    correct: bool,
    failure_reason: str,
) -> dict[str, bool]:
    """Infer teacher-facing check booleans from GenEval metadata and reason."""

    checks = base_checks(metadata, expected)
    if correct:
        return checks

    failed = failed_check_names(metadata, expected, detected, failure_reason)
    if not failed:
        failed = {primary_check_name(metadata, expected)}
    for name in failed:
        checks[name] = False
    return checks


def base_checks(metadata: dict[str, Any], expected: dict[str, Any]) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    if expected.get("objects"):
        checks["object_presence"] = True
    tag = str(metadata.get("tag", ""))
    counts = expected.get("count") if isinstance(expected.get("count"), dict) else {}
    if tag == "counting" or any(_safe_int(value, 1) > 1 for value in counts.values()):
        checks["counting"] = True
    if expected.get("color"):
        checks["color_binding"] = True
    if expected.get("spatial"):
        checks["spatial_relation"] = True
    if expected.get("exclude"):
        checks["extra_object"] = True
    return checks


def failed_check_names(
    metadata: dict[str, Any],
    expected: dict[str, Any],
    detected: list[dict[str, Any]],
    failure_reason: str,
) -> set[str]:
    failed: set[str] = set()
    counts = detected_counts(detected)
    tag = str(metadata.get("tag", ""))

    for target, expected_count in (expected.get("count") or {}).items():
        expected_count = _safe_int(expected_count, 1)
        found = counts.get(str(target), 0)
        if found >= expected_count:
            continue
        if expected_count > 1 or tag == "counting":
            failed.add("counting")
        if found == 0:
            failed.add("object_presence")

    reason = failure_reason.lower()
    color_pattern = "|".join(sorted(GENEVAL_COLORS))
    if re.search(rf"expected\s+({color_pattern})\s+.+?>=\d+", reason):
        failed.add("color_binding")
    if "no target" in reason or " target" in reason:
        failed.add("spatial_relation")
    if re.search(r"expected\s+.+?<\d+,\s*found\s+\d+", reason):
        failed.add("extra_object")
    for relation in ("left of", "right of", "above", "below"):
        if relation in reason:
            failed.add("spatial_relation")
    return failed


def primary_check_name(metadata: dict[str, Any], expected: dict[str, Any]) -> str:
    tag = str(metadata.get("tag", ""))
    if tag == "counting":
        return "counting"
    if tag in {"colors", "color_attribution"} or expected.get("color"):
        return "color_binding"
    if tag == "position" or expected.get("spatial"):
        return "spatial_relation"
    return "object_presence"


def candidate_identity(
    row: dict[str, Any],
    metadata: dict[str, Any],
    *,
    index: int = 0,
) -> tuple[str, str, int]:
    """Return ``sample_id``, ``candidate_id`` and candidate index."""

    filename = str(row.get("filename") or row.get("image_path") or "")
    path = Path(filename)
    sample_id = str(metadata.get("id") or metadata.get("sample_id") or "").strip()
    candidate_index = index
    if path.name:
        stem = path.stem
        if stem.isdigit():
            candidate_index = int(stem)
    if not sample_id:
        if path.parent.name == "samples" and path.parent.parent.name:
            sample_id = path.parent.parent.name
        else:
            sample_id = str(row.get("sample_id") or f"sample_{index:05d}")
    candidate_id = f"{sample_id}_cand_{candidate_index:02d}"
    return sample_id, candidate_id, candidate_index


def detected_counts(detected: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in detected:
        label = str(item.get("label", "")).strip()
        if not label:
            continue
        counts[label] = counts.get(label, 0) + 1
    return counts


def parse_json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    data = json.loads(value)
    return data if isinstance(data, dict) else None


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
