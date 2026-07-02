"""Normalized evaluator report schemas for Geneval/Geneval2 feedback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CRITICAL_FAILURE_TYPES = {
    "missing_object",
    "extra_object",
    "forbidden_object_present",
    "count_mismatch",
    "color_mismatch",
    "attribute_mismatch",
    "spatial_mismatch",
    "relation_mismatch",
    "action_mismatch",
}


@dataclass
class NormalizedConstraint:
    type: str
    target: str
    expected: Any = None
    detected: Any = None
    status: str = "unknown"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "target": self.target,
            "expected": self.expected,
            "detected": self.detected,
            "status": self.status,
            "details": dict(self.details),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedConstraint":
        return cls(
            type=str(data.get("type", "")).strip(),
            target=str(data.get("target", "")).strip(),
            expected=data.get("expected"),
            detected=data.get("detected"),
            status=str(data.get("status", "unknown")).strip() or "unknown",
            details=dict(data.get("details") or {}),
        )


@dataclass
class NormalizedEvalReport:
    score: float
    passed_constraints: list[NormalizedConstraint] = field(default_factory=list)
    failed_constraints: list[NormalizedConstraint] = field(default_factory=list)
    uncertain_constraints: list[NormalizedConstraint] = field(default_factory=list)
    critical_failure_types: list[str] = field(default_factory=list)
    raw_report: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.critical_failure_types:
            self.critical_failure_types = sorted(
                {
                    constraint.type
                    for constraint in self.failed_constraints
                    if constraint.type in CRITICAL_FAILURE_TYPES
                }
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": float(self.score),
            "passed_constraints": [item.to_dict() for item in self.passed_constraints],
            "failed_constraints": [item.to_dict() for item in self.failed_constraints],
            "uncertain_constraints": [item.to_dict() for item in self.uncertain_constraints],
            "critical_failure_types": list(self.critical_failure_types),
            "raw_report": self.raw_report,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedEvalReport":
        return cls(
            score=float(data.get("score", 0.0)),
            passed_constraints=_constraints(data.get("passed_constraints"), status="passed"),
            failed_constraints=_constraints(data.get("failed_constraints"), status="failed"),
            uncertain_constraints=_constraints(data.get("uncertain_constraints"), status="uncertain"),
            critical_failure_types=_strings(data.get("critical_failure_types")),
            raw_report=data.get("raw_report") if isinstance(data.get("raw_report"), dict) else None,
        )

    def failure_type_set(self) -> set[str]:
        return {item.type for item in self.failed_constraints if item.type}


def _constraints(value: Any, *, status: str) -> list[NormalizedConstraint]:
    if not isinstance(value, list):
        return []
    constraints: list[NormalizedConstraint] = []
    for item in value:
        if isinstance(item, dict):
            constraint = NormalizedConstraint.from_dict(item)
        else:
            constraint = NormalizedConstraint(type=str(item), target=str(item))
        if constraint.status == "unknown":
            constraint.status = status
        constraints.append(constraint)
    return constraints


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
