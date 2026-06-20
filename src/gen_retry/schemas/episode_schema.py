"""Typed schemas for visual retry episodes.

The collector uses stdlib dataclasses instead of Pydantic so mock mode stays
dependency-free on the local machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


TEACHER_DECISIONS = {"retry", "submit", "abandon"}
ACTION_TYPES = {"image_edit", "rewrite_prompt", "submit", "abandon"}
ATTEMPT_TYPES = {"initial_generation", "retry_edit", "retry_regeneration"}


@dataclass
class Constraint:
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
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Constraint":
        return cls(
            type=str(data.get("type", "")),
            target=str(data.get("target", "")),
            expected=data.get("expected"),
            detected=data.get("detected"),
            status=str(data.get("status", "unknown")),
            details=dict(data.get("details") or {}),
        )


@dataclass
class NormalizedGenevalReport:
    score: float
    passed_constraints: list[Constraint] = field(default_factory=list)
    failed_constraints: list[Constraint] = field(default_factory=list)
    uncertain_constraints: list[Constraint] = field(default_factory=list)
    raw_report: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": float(self.score),
            "passed_constraints": [item.to_dict() for item in self.passed_constraints],
            "failed_constraints": [item.to_dict() for item in self.failed_constraints],
            "uncertain_constraints": [item.to_dict() for item in self.uncertain_constraints],
            "raw_report": self.raw_report,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedGenevalReport":
        return cls(
            score=float(data.get("score", 0.0)),
            passed_constraints=[
                Constraint.from_dict(item)
                for item in data.get("passed_constraints", [])
                if isinstance(item, dict)
            ],
            failed_constraints=[
                Constraint.from_dict(item)
                for item in data.get("failed_constraints", [])
                if isinstance(item, dict)
            ],
            uncertain_constraints=[
                Constraint.from_dict(item)
                for item in data.get("uncertain_constraints", [])
                if isinstance(item, dict)
            ],
            raw_report=data.get("raw_report") if isinstance(data.get("raw_report"), dict) else None,
        )


@dataclass
class TeacherAction:
    decision: str
    failure_types: list[str] = field(default_factory=list)
    diagnosis: str = ""
    preserve_constraints: list[str] = field(default_factory=list)
    repair_constraints: list[str] = field(default_factory=list)
    action_type: str = "submit"
    skill: str = ""
    edit_instruction: str = ""
    retry_prompt: str | None = None
    regression_risks: list[str] = field(default_factory=list)
    expected_improvement: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "failure_types": list(self.failure_types),
            "diagnosis": self.diagnosis,
            "preserve_constraints": list(self.preserve_constraints),
            "repair_constraints": list(self.repair_constraints),
            "action_type": self.action_type,
            "skill": self.skill,
            "edit_instruction": self.edit_instruction,
            "retry_prompt": self.retry_prompt,
            "regression_risks": list(self.regression_risks),
            "expected_improvement": list(self.expected_improvement),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TeacherAction":
        return cls(
            decision=str(data.get("decision", "")),
            failure_types=_list_strings(data.get("failure_types")),
            diagnosis=str(data.get("diagnosis", "")),
            preserve_constraints=_list_strings(data.get("preserve_constraints")),
            repair_constraints=_list_strings(data.get("repair_constraints")),
            action_type=str(data.get("action_type", "")),
            skill=str(data.get("skill", "")),
            edit_instruction=str(data.get("edit_instruction", "")),
            retry_prompt=data.get("retry_prompt") if isinstance(data.get("retry_prompt"), str) else None,
            regression_risks=_list_strings(data.get("regression_risks")),
            expected_improvement=_list_strings(data.get("expected_improvement")),
        )


@dataclass
class Attempt:
    round: int
    attempt_type: str
    prompt: str
    image_path: str
    geneval_report: NormalizedGenevalReport
    teacher_action: TeacherAction | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "attempt_type": self.attempt_type,
            "prompt": self.prompt,
            "image_path": self.image_path,
            "geneval_report": self.geneval_report.to_dict(),
            "teacher_action": self.teacher_action.to_dict() if self.teacher_action else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Attempt":
        action = data.get("teacher_action")
        return cls(
            round=int(data.get("round", 0)),
            attempt_type=str(data.get("attempt_type", "")),
            prompt=str(data.get("prompt", "")),
            image_path=str(data.get("image_path", "")),
            geneval_report=NormalizedGenevalReport.from_dict(dict(data.get("geneval_report") or {})),
            teacher_action=TeacherAction.from_dict(action) if isinstance(action, dict) else None,
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class Episode:
    id: str
    original_prompt: str
    attempts: list[Attempt] = field(default_factory=list)
    final_outcome: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "original_prompt": self.original_prompt,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "final_outcome": self.final_outcome,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Episode":
        return cls(
            id=str(data.get("id", "")),
            original_prompt=str(data.get("original_prompt", "")),
            attempts=[
                Attempt.from_dict(item)
                for item in data.get("attempts", [])
                if isinstance(item, dict)
            ],
            final_outcome=str(data.get("final_outcome", "")),
            metadata=dict(data.get("metadata") or {}),
        )


def _list_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]

