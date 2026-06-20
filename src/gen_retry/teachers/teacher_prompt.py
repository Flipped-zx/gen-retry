"""Prompt builder for real teacher adapters."""

from __future__ import annotations

import json
from typing import Any

from gen_retry.skills.skill_library import available_skills


TEACHER_SYSTEM_PROMPT = (
    "You are a visual retry teacher. Choose the next action from Geneval-style "
    "diagnostics. Preserve passed constraints, repair failed constraints, and "
    "return strict JSON only. The evaluator, not you, decides whether a retry succeeded."
)


def build_teacher_payload(state: dict[str, Any]) -> list[dict[str, str]]:
    payload = {
        "original_prompt": state.get("original_prompt", ""),
        "current_image_path": state.get("current_image_path", ""),
        "geneval_report": state.get("geneval_report", {}),
        "history_summary": state.get("history_summary", ""),
        "retry_budget_left": state.get("retry_budget_left", 0),
        "available_skills": available_skills(),
        "output_contract": {
            "decision": "retry | submit | abandon",
            "failure_types": ["string"],
            "diagnosis": "string",
            "preserve_constraints": ["string"],
            "repair_constraints": ["string"],
            "action_type": "image_edit | rewrite_prompt | submit | abandon",
            "skill": "string",
            "edit_instruction": "string",
            "retry_prompt": "string or null",
            "regression_risks": ["string"],
            "expected_improvement": ["string"],
        },
    }
    return [
        {"role": "system", "content": TEACHER_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]

