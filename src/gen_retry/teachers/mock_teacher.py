"""Deterministic teacher for mock visual retry episodes."""

from __future__ import annotations

from typing import Any

from gen_retry.schemas.actions import InitialPlanAction, RetryReplanAction
from gen_retry.schemas.episode_schema import Constraint, TeacherAction
from gen_retry.schemas.reports import NormalizedEvalReport
from gen_retry.skills.skill_library import skill_for_failure_type
from gen_retry.teachers.base import BaseTeacher


class MockTeacher(BaseTeacher):
    """Choose deterministic valid actions from normalized failed constraints."""

    name = "mock_teacher"

    def initial_plan(
        self,
        *,
        original_prompt: str,
        evaluator_type: str = "geneval",
        prompt_metadata: dict[str, Any] | None = None,
    ) -> InitialPlanAction:
        _ = evaluator_type, prompt_metadata
        lower = original_prompt.lower()
        skills = _skills_for_prompt(lower)
        action = InitialPlanAction(
            parsed_constraints=_parsed_constraints(original_prompt),
            selected_skills=skills,
            generation_strategy=(
                "Generate a single clear scene. Keep all requested objects separated, "
                "visible, countable, and bound to their requested attributes."
            ),
            initial_prompt=(
                f"{original_prompt}. Clear composition, all requested objects fully visible, "
                "exact counts, correct attribute binding, no extra objects."
            ),
            generation_guards=[
                "Do not add unrequested objects.",
                "Keep object counts visually separable.",
                "Avoid occlusion of required objects.",
            ],
        )
        action.validate()
        return action

    def retry_replan(self, state: dict[str, Any]) -> RetryReplanAction:
        report = NormalizedEvalReport.from_dict(dict(state.get("normalized_eval_report") or {}))
        failed = report.failed_constraints
        previous_skills = [
            str(item)
            for item in state.get("previous_selected_skills", [])
            if str(item).strip()
        ]
        if not failed:
            raise ValueError("retry_replan should not be called when the report already passes")
        failure_types = sorted({item.type for item in failed if item.type})
        new_skills = sorted({skill_for_failure_type(item.type) for item in failed if item.type})
        preserve = [_preserve_text(Constraint.from_dict(item.to_dict())) for item in report.passed_constraints]
        repair = [_repair_text(Constraint.from_dict(item.to_dict())) for item in failed]
        retry_prompt = _replan_prompt(
            str(state.get("original_prompt", "")),
            repair,
            preserve,
            failure_types,
        )
        action = RetryReplanAction(
            failure_types=failure_types,
            diagnosis="; ".join(
                _diagnosis(Constraint.from_dict(item.to_dict())) for item in failed
            ),
            previous_plan_error={
                "error_source": _error_source(failure_types),
                "details": "The previous generation prompt did not make the failed constraints explicit enough.",
            },
            skill_revision={
                "previous_skills": previous_skills,
                "new_skills": new_skills,
                "reason": "Add skills that directly address the failed verifier constraints.",
            },
            preserve_constraints=preserve or ["Preserve all constraints that already passed."],
            repair_constraints=repair,
            regeneration_strategy=(
                "Regenerate the whole image with the original requirements plus explicit repair clauses; "
                "do not edit the previous image."
            ),
            retry_prompt=retry_prompt,
            expected_improvement=[
                "Failed constraints should become more explicit and easier for the frozen generator to satisfy."
            ],
            regression_risks=[
                "Previously correct objects or attributes could change during regeneration.",
                "Tighter repair wording could introduce extra objects if negative constraints are weak.",
            ],
        )
        action.validate()
        return action

    def act(self, state: dict[str, Any]) -> TeacherAction:
        """Legacy action shape for older policy-only collector tests."""
        report = state.get("geneval_report") or {}
        failed = [
            Constraint.from_dict(item)
            for item in report.get("failed_constraints", [])
            if isinstance(item, dict)
        ]
        passed = [
            Constraint.from_dict(item)
            for item in report.get("passed_constraints", [])
            if isinstance(item, dict)
        ]
        if not failed:
            return TeacherAction(
                decision="submit",
                failure_types=[],
                diagnosis="All tracked Geneval constraints passed.",
                preserve_constraints=[_preserve_text(item) for item in passed],
                repair_constraints=[],
                action_type="submit",
                skill="",
                edit_instruction="",
                retry_prompt=None,
                regression_risks=[],
                expected_improvement=["No retry is needed."],
            )

        first = failed[0]
        failure_type = first.type
        skill = skill_for_failure_type(failure_type)
        repair = _repair_text(first)
        preserve = [_preserve_text(item) for item in passed] or [
            "Preserve constraints that already passed."
        ]
        prompt = str(state.get("original_prompt", "")).strip()
        retry_prompt = _retry_prompt(prompt, repair, preserve)
        return TeacherAction(
            decision="retry",
            failure_types=sorted({item.type for item in failed}),
            diagnosis=_diagnosis(first),
            preserve_constraints=preserve,
            repair_constraints=[_repair_text(item) for item in failed],
            action_type="rewrite_prompt",
            skill=skill,
            edit_instruction=repair,
            retry_prompt=retry_prompt,
            regression_risks=[
                "The retry could regress constraints that already passed.",
                "The edit could introduce new objects or change object attributes.",
            ],
            expected_improvement=[
                "The retry should reduce failed Geneval constraints without introducing new critical failures."
            ],
        )


def _diagnosis(constraint: Constraint) -> str:
    return (
        f"Geneval reports {constraint.type} for {constraint.target}: "
        f"expected {constraint.expected}, detected {constraint.detected}."
    )


def _repair_text(constraint: Constraint) -> str:
    if constraint.type == "count_mismatch":
        return f"Adjust {constraint.target} to match the expected count: {constraint.expected}."
    if constraint.type == "color_mismatch":
        return f"Correct {constraint.target} to the expected color or attribute: {constraint.expected}."
    if constraint.type == "spatial_mismatch":
        return f"Move {constraint.target} to satisfy the expected spatial relation: {constraint.expected}."
    if constraint.type == "missing_object":
        return f"Add the missing required object: {constraint.target}."
    if constraint.type == "extra_object":
        return f"Remove the extra forbidden object: {constraint.target}."
    return f"Repair {constraint.type} for {constraint.target}."


def _preserve_text(constraint: Constraint) -> str:
    return f"Keep {constraint.target} {constraint.type} as passed."


def _retry_prompt(prompt: str, repair: str, preserve: list[str]) -> str:
    parts = [prompt or "Generate the requested image."]
    parts.append("Repair: " + repair)
    if preserve:
        parts.append("Preserve: " + " ".join(preserve))
    return " ".join(parts)


def _replan_prompt(prompt: str, repairs: list[str], preserve: list[str], failure_types: list[str]) -> str:
    parts = [
        prompt or "Generate the requested image.",
        "Regenerate from scratch; do not edit a previous image.",
        "Explicit repairs: " + " ".join(repairs),
    ]
    if preserve:
        parts.append("Preserve verified constraints: " + " ".join(preserve))
    if "extra_object" in failure_types:
        parts.append("Negative constraint: do not include extra or duplicate objects.")
    parts.append("Use a clear, uncluttered composition with all required objects visible.")
    return " ".join(parts)


def _skills_for_prompt(prompt: str) -> list[str]:
    skills = {"object_presence", "clarity_visibility"}
    if any(word in prompt for word in ("one", "two", "three", "four", "five", "six", "count")):
        skills.add("quantity_counting")
    if any(word in prompt for word in ("red", "blue", "green", "yellow", "black", "white", "small", "large")):
        skills.add("attribute_binding")
    if any(word in prompt for word in ("left", "right", "above", "below", "under", "over", "next to")):
        skills.add("spatial_layout")
    if "no extra" in prompt or "without" in prompt:
        skills.add("negative_constraints")
    if "and" in prompt or "," in prompt:
        skills.add("multi_object_composition")
    return sorted(skills)


def _parsed_constraints(prompt: str) -> dict[str, Any]:
    return {
        "objects": _rough_objects(prompt),
        "counts": {},
        "attributes": {},
        "relations": [],
    }


def _rough_objects(prompt: str) -> list[str]:
    stop = {
        "a",
        "an",
        "the",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "red",
        "blue",
        "green",
        "yellow",
        "black",
        "white",
        "small",
        "large",
        "with",
        "and",
        "no",
        "extra",
        "objects",
        "object",
        "left",
        "right",
        "under",
        "above",
        "below",
        "of",
        "on",
        "in",
        "to",
    }
    words = [word.strip(".,") for word in prompt.lower().split()]
    return sorted({word for word in words if word and word not in stop})[:8]


def _error_source(failure_types: list[str]) -> str:
    if any(item in failure_types for item in ("missing_object", "extra_object")):
        return "constraint_parsing_or_negative_prompt"
    if any(item in failure_types for item in ("count_mismatch", "color_mismatch", "attribute_mismatch")):
        return "prompt_specificity"
    if any(item in failure_types for item in ("spatial_mismatch", "relation_mismatch")):
        return "layout_strategy"
    return "visibility_or_composition"
