"""Deterministic teacher for mock visual retry episodes."""

from __future__ import annotations

from typing import Any

from gen_retry.schemas.episode_schema import Constraint, TeacherAction
from gen_retry.skills.skill_library import skill_for_failure_type
from gen_retry.teachers.base import BaseTeacher


class MockTeacher(BaseTeacher):
    """Choose a valid action from normalized failed constraints."""

    def act(self, state: dict[str, Any]) -> TeacherAction:
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
            action_type="image_edit",
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
