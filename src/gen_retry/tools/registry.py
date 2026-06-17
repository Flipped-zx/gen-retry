"""Tool registry placeholders for Stage 2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


DEFAULT_TOOLS = {
    "parse_constraints": ToolSpec(
        name="parse_constraints",
        description="Extract object, count, color, and spatial constraints from a prompt.",
        input_schema={"type": "object", "required": ["prompt"]},
    ),
    "generate_image": ToolSpec(
        name="generate_image",
        description="Placeholder for future image generation.",
        input_schema={"type": "object", "required": ["prompt"]},
    ),
    "judge_image": ToolSpec(
        name="judge_image",
        description="Placeholder for future Geneval-compatible image judging.",
        input_schema={"type": "object", "required": ["prompt", "image"]},
    ),
    "query_skill": ToolSpec(
        name="query_skill",
        description="Retrieve skill guidance for a diagnostic failure type.",
        input_schema={"type": "object", "required": ["failure_type"]},
    ),
    "repair_prompt": ToolSpec(
        name="repair_prompt",
        description="Create a targeted repair prompt from preserve candidates and repair targets.",
        input_schema={"type": "object", "required": ["prompt", "normalized_diagnostic"]},
    ),
    "select_best_candidate": ToolSpec(
        name="select_best_candidate",
        description="Placeholder for selecting among retry candidates.",
        input_schema={"type": "object", "required": ["candidates"]},
    ),
    "submit": ToolSpec(
        name="submit",
        description="Submit the selected final candidate.",
        input_schema={"type": "object", "required": ["candidate"]},
    ),
}


def get_tool(name: str) -> ToolSpec | None:
    return DEFAULT_TOOLS.get(name)


def list_tools() -> list[str]:
    return sorted(DEFAULT_TOOLS)
