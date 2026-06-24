"""Planner action schemas for initial planning and verifier-guided re-planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ALLOWED_SKILLS = {
    "object_presence",
    "quantity_counting",
    "attribute_binding",
    "spatial_layout",
    "anti_occlusion",
    "multi_object_composition",
    "clarity_visibility",
    "negative_constraints",
}

DIRECT_EDIT_KEYS = {"edit_instruction", "image_edit", "mask", "bbox", "inpaint", "source_image"}


class ActionValidationError(ValueError):
    """Raised when a planner action violates the macro-action schema."""


@dataclass
class InitialPlanAction:
    action_type: str = "initial_plan"
    parsed_constraints: dict[str, Any] = field(
        default_factory=lambda: {"objects": [], "counts": {}, "attributes": {}, "relations": []}
    )
    selected_skills: list[str] = field(default_factory=list)
    generation_strategy: str = ""
    initial_prompt: str = ""
    generation_guards: list[str] = field(default_factory=list)

    def validate(self) -> None:
        errors: list[str] = []
        if self.action_type != "initial_plan":
            errors.append("action_type must be initial_plan")
        invalid = sorted(set(self.selected_skills) - ALLOWED_SKILLS)
        if invalid:
            errors.append(f"invalid selected_skills: {invalid}")
        if not self.initial_prompt.strip():
            errors.append("initial_prompt is required")
        for key in ("objects", "counts", "attributes", "relations"):
            if key not in self.parsed_constraints:
                errors.append(f"parsed_constraints.{key} is required")
        if errors:
            raise ActionValidationError("; ".join(errors))

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "parsed_constraints": _jsonable_dict(self.parsed_constraints),
            "selected_skills": list(self.selected_skills),
            "generation_strategy": self.generation_strategy,
            "initial_prompt": self.initial_prompt,
            "generation_guards": list(self.generation_guards),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InitialPlanAction":
        action = cls(
            action_type=str(data.get("action_type", "initial_plan")),
            parsed_constraints=_constraints_dict(data.get("parsed_constraints")),
            selected_skills=_strings(data.get("selected_skills")),
            generation_strategy=str(data.get("generation_strategy", "")),
            initial_prompt=str(data.get("initial_prompt", "")),
            generation_guards=_strings(data.get("generation_guards")),
        )
        action.validate()
        return action


@dataclass
class RetryReplanAction:
    action_type: str = "retry_replan"
    decision: str = "regenerate"
    failure_types: list[str] = field(default_factory=list)
    diagnosis: str = ""
    previous_plan_error: dict[str, str] = field(default_factory=lambda: {"error_source": "", "details": ""})
    skill_revision: dict[str, Any] = field(
        default_factory=lambda: {"previous_skills": [], "new_skills": [], "reason": ""}
    )
    preserve_constraints: list[str] = field(default_factory=list)
    repair_constraints: list[str] = field(default_factory=list)
    regeneration_strategy: str = ""
    retry_prompt: str = ""
    expected_improvement: list[str] = field(default_factory=list)
    regression_risks: list[str] = field(default_factory=list)

    def validate(self) -> None:
        errors: list[str] = []
        if self.action_type != "retry_replan":
            errors.append("action_type must be retry_replan")
        if self.decision != "regenerate":
            errors.append("decision must be regenerate")
        if not self.retry_prompt.strip():
            errors.append("retry_prompt is required")
        previous = _strings(self.skill_revision.get("previous_skills"))
        new = _strings(self.skill_revision.get("new_skills"))
        invalid = sorted((set(previous) | set(new)) - ALLOWED_SKILLS)
        if invalid:
            errors.append(f"invalid skill_revision skills: {invalid}")
        payload = self.to_dict(validate=False)
        direct_edit = sorted(DIRECT_EDIT_KEYS & _deep_keys(payload))
        if direct_edit:
            errors.append(f"direct image edit fields are not allowed: {direct_edit}")
        if errors:
            raise ActionValidationError("; ".join(errors))

    def to_dict(self, *, validate: bool = True) -> dict[str, Any]:
        if validate:
            self.validate()
        return {
            "action_type": self.action_type,
            "decision": self.decision,
            "failure_types": list(self.failure_types),
            "diagnosis": self.diagnosis,
            "previous_plan_error": dict(self.previous_plan_error),
            "skill_revision": {
                "previous_skills": _strings(self.skill_revision.get("previous_skills")),
                "new_skills": _strings(self.skill_revision.get("new_skills")),
                "reason": str(self.skill_revision.get("reason", "")),
            },
            "preserve_constraints": list(self.preserve_constraints),
            "repair_constraints": list(self.repair_constraints),
            "regeneration_strategy": self.regeneration_strategy,
            "retry_prompt": self.retry_prompt,
            "expected_improvement": list(self.expected_improvement),
            "regression_risks": list(self.regression_risks),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RetryReplanAction":
        direct_edit = sorted(DIRECT_EDIT_KEYS & _deep_keys(data))
        if direct_edit:
            raise ActionValidationError(f"direct image edit fields are not allowed: {direct_edit}")
        action = cls(
            action_type=str(data.get("action_type", "retry_replan")),
            decision=str(data.get("decision", "regenerate")),
            failure_types=_strings(data.get("failure_types")),
            diagnosis=str(data.get("diagnosis", "")),
            previous_plan_error=_previous_plan_error(data.get("previous_plan_error")),
            skill_revision=_skill_revision(data.get("skill_revision")),
            preserve_constraints=_strings(data.get("preserve_constraints")),
            repair_constraints=_strings(data.get("repair_constraints")),
            regeneration_strategy=str(data.get("regeneration_strategy", "")),
            retry_prompt=str(data.get("retry_prompt", "")),
            expected_improvement=_strings(data.get("expected_improvement")),
            regression_risks=_strings(data.get("regression_risks")),
        )
        action.validate()
        return action


def parse_action(data: dict[str, Any]) -> InitialPlanAction | RetryReplanAction:
    action_type = str(data.get("action_type", "")).strip()
    if action_type == "initial_plan":
        return InitialPlanAction.from_dict(data)
    if action_type == "retry_replan":
        return RetryReplanAction.from_dict(data)
    raise ActionValidationError(f"unknown action_type: {action_type}")


def _empty_constraints() -> dict[str, Any]:
    return {"objects": [], "counts": {}, "attributes": {}, "relations": []}


def _constraints_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return _empty_constraints()
    result = _empty_constraints()
    result.update(value)
    if not isinstance(result["objects"], list):
        result["objects"] = []
    if not isinstance(result["counts"], dict):
        result["counts"] = {}
    if not isinstance(result["attributes"], dict):
        result["attributes"] = {}
    if not isinstance(result["relations"], list):
        result["relations"] = []
    return result


def _previous_plan_error(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"error_source": "", "details": ""}
    return {
        "error_source": str(value.get("error_source", "")),
        "details": str(value.get("details", "")),
    }


def _skill_revision(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"previous_skills": [], "new_skills": [], "reason": ""}
    return {
        "previous_skills": _strings(value.get("previous_skills")),
        "new_skills": _strings(value.get("new_skills")),
        "reason": str(value.get("reason", "")),
    }


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _jsonable_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items()}


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
