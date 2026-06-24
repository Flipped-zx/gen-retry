"""Normalize Geneval and Geneval2-style outputs into a shared report schema."""

from __future__ import annotations

from typing import Any

from gen_retry.schemas.reports import CRITICAL_FAILURE_TYPES, NormalizedConstraint, NormalizedEvalReport


def normalize_eval_report(raw: dict[str, Any], *, evaluator_type: str = "geneval") -> NormalizedEvalReport:
    if evaluator_type == "geneval2":
        return normalize_geneval2_report(raw)
    return normalize_geneval_report(raw)


def normalize_geneval_report(raw: dict[str, Any]) -> NormalizedEvalReport:
    passed = _constraints(raw.get("passed_constraints"), "passed")
    failed = _constraints(raw.get("failed_constraints"), "failed")
    uncertain = _constraints(raw.get("uncertain_constraints"), "uncertain")
    if not failed and raw.get("correct") is False:
        failed.append(
            NormalizedConstraint(
                type=str(raw.get("failure_type", "attribute_mismatch")),
                target=str(raw.get("target", raw.get("prompt", "constraint"))),
                expected=raw.get("expected"),
                detected=raw.get("detected"),
                status="failed",
            )
        )
    score = _score(raw, failed)
    critical = _critical(raw, failed)
    return NormalizedEvalReport(
        score=score,
        passed_constraints=passed,
        failed_constraints=failed,
        uncertain_constraints=uncertain,
        critical_failure_types=critical,
        raw_report=dict(raw),
    )


def normalize_geneval2_report(raw: dict[str, Any]) -> NormalizedEvalReport:
    passed = _constraints(raw.get("passed_constraints"), "passed")
    failed = _constraints(raw.get("failed_constraints"), "failed")
    uncertain = _constraints(raw.get("uncertain_constraints"), "uncertain")
    for source_key in ("atoms", "vqa", "skills"):
        items = raw.get(source_key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            constraint = _geneval2_constraint(item, source_key)
            status = str(item.get("status", item.get("result", ""))).lower()
            passed_flag = item.get("passed")
            if passed_flag is True or status in {"pass", "passed", "correct", "ok"}:
                passed.append(constraint)
            elif passed_flag is False or status in {"fail", "failed", "incorrect"}:
                failed.append(constraint)
            else:
                uncertain.append(constraint)
    score = _score(raw, failed)
    critical = _critical(raw, failed)
    return NormalizedEvalReport(
        score=score,
        passed_constraints=passed,
        failed_constraints=failed,
        uncertain_constraints=uncertain,
        critical_failure_types=critical,
        raw_report=dict(raw),
    )


def _constraints(value: Any, default_status: str) -> list[NormalizedConstraint]:
    if not isinstance(value, list):
        return []
    result: list[NormalizedConstraint] = []
    for item in value:
        if isinstance(item, dict):
            constraint = NormalizedConstraint.from_dict(item)
            if constraint.status == "unknown":
                constraint.status = default_status
            result.append(constraint)
    return result


def _geneval2_constraint(item: dict[str, Any], source_key: str) -> NormalizedConstraint:
    failure_type = str(
        item.get("failure_type")
        or item.get("type")
        or item.get("skill")
        or _failure_type_from_source(source_key)
    )
    return NormalizedConstraint(
        type=failure_type,
        target=str(item.get("target", item.get("object", item.get("question", source_key)))),
        expected=item.get("expected", item.get("answer")),
        detected=item.get("detected", item.get("prediction")),
        status=str(item.get("status", "unknown")),
        details={key: value for key, value in item.items() if key not in {"expected", "detected"}},
    )


def _failure_type_from_source(source_key: str) -> str:
    if source_key == "vqa":
        return "attribute_mismatch"
    if source_key == "skills":
        return "relation_mismatch"
    return "missing_object"


def _score(raw: dict[str, Any], failed: list[NormalizedConstraint]) -> float:
    value = raw.get("score")
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    if raw.get("correct") is True:
        return 1.0
    if raw.get("correct") is False:
        return 0.0
    return 0.0 if failed else 1.0


def _critical(raw: dict[str, Any], failed: list[NormalizedConstraint]) -> list[str]:
    explicit = raw.get("critical_failure_types")
    if isinstance(explicit, list):
        return sorted({str(item) for item in explicit if str(item).strip()})
    return sorted({item.type for item in failed if item.type in CRITICAL_FAILURE_TYPES})
