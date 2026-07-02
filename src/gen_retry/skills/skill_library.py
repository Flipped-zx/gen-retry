"""Fixed skill library for visual planning and verifier-guided re-planning."""

from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(frozen=True)
class SkillGuidance:
    name: str
    supported_failure_types: tuple[str, ...]
    guidance: str
    prompt_hints: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "supported_failure_types": list(self.supported_failure_types),
            "guidance": self.guidance,
            "prompt_hints": list(self.prompt_hints),
        }


SKILL_LIBRARY = {
    "object_presence": SkillGuidance(
        name="object_presence",
        supported_failure_types=("missing_object",),
        guidance="Ensure every required object is explicitly named, visible, and not cropped out.",
        prompt_hints=(
            "Name the object directly.",
            "Require it to be fully visible and easy to identify.",
            "Avoid background clutter that could hide the object.",
        ),
    ),
    "quantity_counting": SkillGuidance(
        name="quantity_counting",
        supported_failure_types=("count_mismatch", "missing_instance", "extra_instance"),
        guidance=(
            "State the exact number, require separate visible instances, avoid overlap, "
            "avoid merging, and make each instance countable."
        ),
        prompt_hints=(
            "Repeat the exact count in words or digits.",
            "Ask for separate, non-overlapping instances.",
            "Use a simple layout that makes counting easy.",
        ),
    ),
    "attribute_binding": SkillGuidance(
        name="attribute_binding",
        supported_failure_types=("color_mismatch", "attribute_mismatch"),
        guidance=(
            "Bind each attribute to the target object explicitly. Avoid leaking the "
            "attribute to other objects."
        ),
        prompt_hints=(
            "Use object-attribute pairs such as 'the red cube' and 'the blue sphere'.",
            "Restate which object should not receive the attribute when needed.",
            "Keep unrelated objects visually distinct.",
        ),
    ),
    "spatial_layout": SkillGuidance(
        name="spatial_layout",
        supported_failure_types=("spatial_mismatch", "relation_mismatch"),
        guidance=(
            "State the relative positions clearly. Use unambiguous left/right/above/below/"
            "in-front/behind relations and a simple composition."
        ),
        prompt_hints=(
            "Name subject, relation, and object in one sentence.",
            "Use foreground/background or left/right anchoring for clarity.",
            "Avoid layouts where objects overlap or swap positions.",
        ),
    ),
    "anti_occlusion": SkillGuidance(
        name="anti_occlusion",
        supported_failure_types=("occluded_object", "low_visibility"),
        guidance="Arrange objects so required entities are not hidden, merged, or blocked.",
        prompt_hints=(
            "Ask for every required object to be fully visible.",
            "Avoid overlap and heavy occlusion.",
            "Use spacing or staggered placement for crowded scenes.",
        ),
    ),
    "multi_object_composition": SkillGuidance(
        name="multi_object_composition",
        supported_failure_types=("missing_object", "count_mismatch", "spatial_mismatch"),
        guidance="Keep several objects distinct, complete, and jointly visible in one coherent scene.",
        prompt_hints=(
            "List all required objects together.",
            "Use a clean composition with each object separated enough to verify.",
            "Avoid adding unrequested objects.",
        ),
    ),
    "clarity_visibility": SkillGuidance(
        name="clarity_visibility",
        supported_failure_types=("low_visibility", "missing_object"),
        guidance="Make required objects clear, centered enough, unobstructed, and easy to verify.",
        prompt_hints=(
            "Use clear lighting and simple background.",
            "Require the target to be recognizable and not tiny.",
            "Avoid blur, extreme crop, or ambiguity.",
        ),
    ),
    "negative_constraints": SkillGuidance(
        name="negative_constraints",
        supported_failure_types=("extra_object", "forbidden_object_present", "extra_instance"),
        guidance="Avoid forbidden or extra objects while preserving required content.",
        prompt_hints=(
            "Say 'no extra objects' or name forbidden extras explicitly.",
            "Keep the scene minimal and uncluttered.",
            "Do not add props, text, or decorative items unless requested.",
        ),
    ),
}

SKILL_DESCRIPTIONS = {name: item.guidance for name, item in SKILL_LIBRARY.items()}


def skill_for_failure_type(failure_type: str) -> str:
    return SKILL_BY_FAILURE_TYPE.get(failure_type, "clarity_visibility")


def available_skills() -> dict[str, str]:
    return dict(SKILL_DESCRIPTIONS)


def get_skill_guidance(skill_name: str) -> SkillGuidance:
    if skill_name not in SKILL_LIBRARY:
        raise KeyError(f"unknown skill: {skill_name}")
    return SKILL_LIBRARY[skill_name]


def query_skill(skill_name: str) -> dict[str, object]:
    return get_skill_guidance(skill_name).to_dict()
