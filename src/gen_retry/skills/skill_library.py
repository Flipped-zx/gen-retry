"""Fixed skill library for visual planning and verifier-guided re-planning."""

from __future__ import annotations


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


SKILL_BY_FAILURE_TYPE = {
    "count_mismatch": "quantity_counting",
    "missing_instance": "quantity_counting",
    "extra_instance": "quantity_counting",
    "color_mismatch": "attribute_binding",
    "attribute_mismatch": "attribute_binding",
    "spatial_mismatch": "spatial_layout",
    "relation_mismatch": "spatial_layout",
    "missing_object": "object_presence",
    "extra_object": "negative_constraints",
    "forbidden_object_present": "negative_constraints",
    "occluded_object": "anti_occlusion",
    "low_visibility": "clarity_visibility",
}


SKILL_DESCRIPTIONS = {
    "object_presence": "Ensure required objects are explicitly present and visible.",
    "quantity_counting": "Repair exact counts while preserving object attributes.",
    "attribute_binding": "Repair object-to-attribute binding errors.",
    "spatial_layout": "Repair relative placement and layout constraints.",
    "anti_occlusion": "Arrange objects so required entities are not hidden or blocked.",
    "multi_object_composition": "Keep several objects distinct, complete, and jointly visible.",
    "clarity_visibility": "Make required objects clear, centered enough, and easy to verify.",
    "negative_constraints": "Avoid forbidden or extra objects while preserving required content.",
}


def skill_for_failure_type(failure_type: str) -> str:
    return SKILL_BY_FAILURE_TYPE.get(failure_type, "clarity_visibility")


def available_skills() -> dict[str, str]:
    return dict(SKILL_DESCRIPTIONS)
