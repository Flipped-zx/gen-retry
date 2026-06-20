"""Normalize mock or real Geneval-style reports for retry collection."""

from __future__ import annotations

from typing import Any

from gen_retry.schemas.episode_schema import Constraint, NormalizedGenevalReport


def normalize_geneval_report(raw: dict[str, Any]) -> NormalizedGenevalReport:
    """Convert a simple raw report dictionary into a normalized report."""

    return NormalizedGenevalReport(
        score=float(raw.get("score", 0.0)),
        passed_constraints=_constraints(raw.get("passed_constraints"), "passed"),
        failed_constraints=_constraints(raw.get("failed_constraints"), "failed"),
        uncertain_constraints=_constraints(raw.get("uncertain_constraints"), "uncertain"),
        raw_report=raw,
    )


def report_from_failure(
    *,
    failure_type: str | None,
    target: str,
    expected: Any,
    detected: Any,
    score: float,
) -> NormalizedGenevalReport:
    if not failure_type:
        return NormalizedGenevalReport(
            score=score,
            passed_constraints=[
                Constraint(
                    type="all_constraints",
                    target=target or "prompt",
                    expected=expected,
                    detected=detected,
                    status="passed",
                )
            ],
            failed_constraints=[],
            uncertain_constraints=[],
            raw_report={"mock": True, "failure_type": None},
        )
    return NormalizedGenevalReport(
        score=score,
        passed_constraints=[],
        failed_constraints=[
            Constraint(
                type=failure_type,
                target=target,
                expected=expected,
                detected=detected,
                status="failed",
            )
        ],
        uncertain_constraints=[],
        raw_report={"mock": True, "failure_type": failure_type},
    )


def _constraints(value: Any, default_status: str) -> list[Constraint]:
    if not isinstance(value, list):
        return []
    out: list[Constraint] = []
    for item in value:
        if isinstance(item, Constraint):
            out.append(item)
        elif isinstance(item, dict):
            data = dict(item)
            data.setdefault("status", default_status)
            out.append(Constraint.from_dict(data))
    return out

