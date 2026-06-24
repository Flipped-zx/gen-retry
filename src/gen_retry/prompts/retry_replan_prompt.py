"""Prompt template for verifier-guided retry re-planning."""

from __future__ import annotations

import json
from typing import Any

from gen_retry.schemas.actions import ALLOWED_SKILLS


RETRY_REPLAN_SYSTEM_PROMPT = """You are a verifier-guided image generation re-planning agent.
Return JSON only. Retry means regeneration from a new prompt, not direct image edit.
Use the normalized Geneval/Geneval2 feedback to diagnose failed constraints,
explain weakness in the previous plan/prompt/skill usage, revise skills if needed,
and produce a new retry_prompt for regeneration.
The decision must be "regenerate" whenever a retry is requested.
If the report already passes, do not produce retry_replan.
Do not include image edit instructions, masks, bounding boxes, source image edits, or inpainting fields.
"""


def build_retry_replan_messages(
    *,
    original_prompt: str,
    previous_initial_plan: dict[str, Any],
    previous_prompt: str,
    previous_selected_skills: list[str],
    normalized_eval_report: dict[str, Any],
    retry_history: list[dict[str, Any]],
    retry_budget_left: int,
) -> list[dict[str, str]]:
    state = {
        "original_prompt": original_prompt,
        "previous_initial_plan": previous_initial_plan,
        "previous_prompt": previous_prompt,
        "previous_selected_skills": previous_selected_skills,
        "normalized_eval_report": normalized_eval_report,
        "retry_history": retry_history,
        "retry_budget_left": retry_budget_left,
        "allowed_skills": sorted(ALLOWED_SKILLS),
        "output_schema": {
            "action_type": "retry_replan",
            "decision": "regenerate",
            "failure_types": [],
            "diagnosis": "",
            "previous_plan_error": {"error_source": "", "details": ""},
            "skill_revision": {"previous_skills": [], "new_skills": [], "reason": ""},
            "preserve_constraints": [],
            "repair_constraints": [],
            "regeneration_strategy": "",
            "retry_prompt": "",
            "expected_improvement": [],
            "regression_risks": [],
        },
    }
    return [
        {"role": "system", "content": RETRY_REPLAN_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)},
    ]
