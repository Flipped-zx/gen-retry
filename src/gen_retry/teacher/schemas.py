"""Strict schema for teacher retry actions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from gen_retry.tools.skills import DEFAULT_SKILLS


DECISIONS = {"retry", "submit", "discard"}
REQUIRED_ACTION_KEYS = (
    "decision",
    "failure_types",
    "skills_to_call",
    "preserve_constraints",
    "repair_constraints",
    "repair_strategy",
    "retry_prompt",
    "expected_improvement",
    "regression_risks",
)
ALLOWED_ACTION_KEYS = set(REQUIRED_ACTION_KEYS)
ALLOWED_SKILLS = set(DEFAULT_SKILLS)

TEACHER_RETRY_ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": list(REQUIRED_ACTION_KEYS),
    "properties": {
        "decision": {"type": "string", "enum": sorted(DECISIONS)},
        "failure_types": {"type": "array", "items": {"type": "string"}},
        "skills_to_call": {"type": "array", "items": {"type": "string", "enum": sorted(ALLOWED_SKILLS)}},
        "preserve_constraints": {"type": "array", "items": {"type": "string"}},
        "repair_constraints": {"type": "array", "items": {"type": "string"}},
        "repair_strategy": {"type": "string"},
        "retry_prompt": {"type": "string"},
        "expected_improvement": {"type": "array", "items": {"type": "string"}},
        "regression_risks": {"type": "array", "items": {"type": "string"}},
    },
}


class TeacherActionValidationError(ValueError):
    """Raised when a teacher retry action violates the strict schema."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class TeacherRetryAction:
    decision: str
    failure_types: tuple[str, ...]
    skills_to_call: tuple[str, ...]
    preserve_constraints: tuple[str, ...]
    repair_constraints: tuple[str, ...]
    repair_strategy: str
    retry_prompt: str
    expected_improvement: tuple[str, ...]
    regression_risks: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "failure_types": list(self.failure_types),
            "skills_to_call": list(self.skills_to_call),
            "preserve_constraints": list(self.preserve_constraints),
            "repair_constraints": list(self.repair_constraints),
            "repair_strategy": self.repair_strategy,
            "retry_prompt": self.retry_prompt,
            "expected_improvement": list(self.expected_improvement),
            "regression_risks": list(self.regression_risks),
        }


def validate_teacher_retry_action(payload: Any) -> TeacherRetryAction:
    """Validate and return a strict TeacherRetryAction."""

    errors: list[str] = []
    if not isinstance(payload, dict):
        raise TeacherActionValidationError(["teacher action must be an object"])

    missing = [key for key in REQUIRED_ACTION_KEYS if key not in payload]
    extra = sorted(set(payload).difference(ALLOWED_ACTION_KEYS))
    if missing:
        errors.append("missing required keys: " + ", ".join(missing))
    if extra:
        errors.append("unexpected keys: " + ", ".join(extra))

    decision = payload.get("decision")
    if not isinstance(decision, str) or decision not in DECISIONS:
        errors.append("decision must be one of: discard, retry, submit")

    list_values: dict[str, tuple[str, ...]] = {}
    for key in (
        "failure_types",
        "skills_to_call",
        "preserve_constraints",
        "repair_constraints",
        "expected_improvement",
        "regression_risks",
    ):
        values = payload.get(key)
        if not isinstance(values, list):
            errors.append(f"{key} must be a list of strings")
            list_values[key] = ()
            continue
        clean: list[str] = []
        for index, value in enumerate(values):
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{key}[{index}] must be a non-empty string")
            else:
                clean.append(value.strip())
        list_values[key] = tuple(clean)

    for skill in list_values.get("skills_to_call", ()):
        if skill not in ALLOWED_SKILLS:
            errors.append(f"unknown skill: {skill}")

    repair_strategy = payload.get("repair_strategy")
    retry_prompt = payload.get("retry_prompt")
    if not isinstance(repair_strategy, str):
        errors.append("repair_strategy must be a string")
        repair_strategy = ""
    if not isinstance(retry_prompt, str):
        errors.append("retry_prompt must be a string")
        retry_prompt = ""

    if decision == "retry":
        if not str(retry_prompt).strip():
            errors.append("retry decision requires a non-empty retry_prompt")
        if not list_values.get("skills_to_call"):
            errors.append("retry decision requires at least one skill")
        if not list_values.get("repair_constraints"):
            errors.append("retry decision requires at least one repair constraint")

    if decision == "submit" and list_values.get("repair_constraints"):
        errors.append("submit decision must not include repair constraints")

    if errors:
        raise TeacherActionValidationError(errors)

    return TeacherRetryAction(
        decision=str(decision),
        failure_types=list_values["failure_types"],
        skills_to_call=list_values["skills_to_call"],
        preserve_constraints=list_values["preserve_constraints"],
        repair_constraints=list_values["repair_constraints"],
        repair_strategy=str(repair_strategy).strip(),
        retry_prompt=str(retry_prompt).strip(),
        expected_improvement=list_values["expected_improvement"],
        regression_risks=list_values["regression_risks"],
    )


def parse_teacher_action_text(text: str) -> TeacherRetryAction:
    """Parse a teacher response string as strict retry-action JSON."""

    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[A-Za-z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    payload = json.loads(cleaned)
    return validate_teacher_retry_action(payload)
