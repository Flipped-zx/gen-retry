"""Skill routing helpers for Geneval retry diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Skill:
    name: str
    failure_types: tuple[str, ...]
    summary: str


DEFAULT_SKILLS = {
    "quantity_counting": Skill(
        name="quantity_counting",
        failure_types=("count_mismatch", "missing_instance", "extra_instance"),
        summary="Repair exact counts while preserving already-correct constraints.",
    ),
    "attribute_binding": Skill(
        name="attribute_binding",
        failure_types=("color_mismatch", "attribute_mismatch", "attribute_leakage"),
        summary="Repair object-to-attribute binding mistakes.",
    ),
    "spatial_layout": Skill(
        name="spatial_layout",
        failure_types=("spatial_mismatch", "relation_mismatch"),
        summary="Repair relative position and layout failures.",
    ),
    "object_presence": Skill(
        name="object_presence",
        failure_types=("missing_object", "forbidden_object_present"),
        summary="Repair missing required objects or unwanted objects.",
    ),
    "object_separation": Skill(
        name="object_separation",
        failure_types=("merged_instances", "ambiguous_instances"),
        summary="Prevent instances from merging or becoming ambiguous.",
    ),
    "visibility_and_anti_occlusion": Skill(
        name="visibility_and_anti_occlusion",
        failure_types=("occluded_object", "low_visibility", "unverifiable_constraint"),
        summary="Make required constraints visible enough for judging.",
    ),
    "preserve_correct_constraints": Skill(
        name="preserve_correct_constraints",
        failure_types=("any_retry",),
        summary="Carry forward constraints that already passed.",
    ),
}


def skill_for_failure_type(failure_type: str) -> Skill:
    for skill in DEFAULT_SKILLS.values():
        if failure_type in skill.failure_types:
            return skill
    return DEFAULT_SKILLS["preserve_correct_constraints"]


def list_skill_names() -> list[str]:
    return sorted(DEFAULT_SKILLS)


def load_skill_names_from_yaml(path: str | Path) -> list[str]:
    """Extract skill names from the simple Stage 2 YAML without a YAML dependency."""

    names: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- name:"):
            _, value = stripped.split(":", 1)
            name = value.strip()
            if name:
                names.append(name)
    return names
