"""Skill routing for visual retry actions."""

from __future__ import annotations


SKILL_BY_FAILURE_TYPE = {
    "count_mismatch": "quantity_counting",
    "missing_instance": "quantity_counting",
    "extra_instance": "quantity_counting",
    "color_mismatch": "attribute_binding",
    "attribute_mismatch": "attribute_binding",
    "spatial_mismatch": "spatial_layout",
    "relation_mismatch": "spatial_layout",
    "missing_object": "object_presence",
    "extra_object": "object_presence",
    "forbidden_object_present": "object_presence",
    "occluded_object": "visibility_and_anti_occlusion",
    "low_visibility": "visibility_and_anti_occlusion",
}


SKILL_DESCRIPTIONS = {
    "quantity_counting": "Repair exact counts while preserving object attributes.",
    "attribute_binding": "Repair object-to-attribute binding errors.",
    "spatial_layout": "Repair relative placement and layout constraints.",
    "object_presence": "Add missing required objects or remove forbidden extras.",
    "visibility_and_anti_occlusion": "Make required objects visible enough for judging.",
    "preserve_correct_constraints": "Carry forward constraints that already passed.",
}


def skill_for_failure_type(failure_type: str) -> str:
    return SKILL_BY_FAILURE_TYPE.get(failure_type, "preserve_correct_constraints")


def available_skills() -> dict[str, str]:
    return dict(SKILL_DESCRIPTIONS)

