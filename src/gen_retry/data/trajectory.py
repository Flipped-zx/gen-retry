"""Data structures for diagnostic-conditioned retry trajectories."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ALLOWED_STEP_TYPES = {
    "user_prompt",
    "parse_constraints",
    "image_generation",
    "judge_diagnostic",
    "tool_call",
    "tool_observation",
    "preserve_plan",
    "repair_prompt",
    "retry_generation",
    "submit",
}

ALLOWED_ROLES = {"system", "user", "assistant", "tool"}


@dataclass(frozen=True)
class TrajectoryStep:
    """One supervised step in a retry trajectory."""

    type: str
    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "type": self.type,
            "role": self.role,
            "content": self.content,
        }
        data.update(self.metadata)
        return data


@dataclass(frozen=True)
class RetryTrajectory:
    """Top-level SFT trajectory record."""

    schema_version: str
    trajectory_id: str
    source_prompt: str
    diagnostic_input: dict[str, Any]
    normalized_diagnostic: dict[str, Any]
    steps: list[TrajectoryStep]
    outcome: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "trajectory_id": self.trajectory_id,
            "source_prompt": self.source_prompt,
            "diagnostic_input": self.diagnostic_input,
            "normalized_diagnostic": self.normalized_diagnostic,
            "steps": [step.to_dict() for step in self.steps],
            "outcome": self.outcome,
        }
