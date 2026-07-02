"""Prompt template for the initial planning macro action."""

from __future__ import annotations

import json
from typing import Any

from gen_retry.schemas.actions import ALLOWED_SKILLS


INITIAL_PLAN_SYSTEM_PROMPT = """You are a compositional image generation planner.
Return exactly one JSON object and nothing else. Do not use markdown fences,
comments, prose explanations, or keys outside the requested schema.
Do not use web search, image search, reference image retrieval, uploaded
references, masks, bounding boxes, inpainting, or direct image editing.
Select skills only from the fixed skill library.
Your job is to parse the user's original image prompt, plan the first generation,
and produce a generator-facing prompt that preserves all explicit constraints.
Be explicit about object counts, count separation, attribute binding, spatial layout,
visibility, and avoiding occlusion when relevant.
Do not invent objects, colors, counts, attributes, actions, or spatial relations
that are not stated or directly implied by the original prompt.
The initial_prompt must be directly usable by a text-to-image generator.
"""


def build_initial_plan_messages(
    *,
    original_prompt: str,
    evaluator_type: str = "geneval",
    prompt_metadata: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    state = {
        "original_prompt": original_prompt,
        "evaluator_type": evaluator_type,
        "prompt_metadata": prompt_metadata or {},
        "allowed_skills": sorted(ALLOWED_SKILLS),
        "output_schema": {
            "action_type": "initial_plan",
            "parsed_constraints": {
                "objects": [],
                "counts": {},
                "attributes": {},
                "relations": [],
            },
            "selected_skills": [],
            "generation_strategy": "",
            "initial_prompt": "",
            "generation_guards": [],
        },
    }
    return [
        {"role": "system", "content": INITIAL_PLAN_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)},
    ]
