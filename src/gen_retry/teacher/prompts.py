"""Prompt templates for teacher retry-action generation."""

from __future__ import annotations

import json
from typing import Any

from gen_retry.teacher.schemas import REQUIRED_ACTION_KEYS
from gen_retry.tools.skills import DEFAULT_SKILLS


TEACHER_SYSTEM_PROMPT = """You are a teacher policy for diagnostic-conditioned image-generation retry training.

You receive a Geneval-style diagnostic for a first image-generation attempt.
Your job is to decide whether to retry, submit, or discard, and to produce one strict JSON object.

Rules:
- Preserve constraints that already passed.
- Repair only failed constraints.
- Route failures to the smallest set of relevant skills.
- Do not invent objects, colors, counts, or spatial relations.
- Return JSON only. Do not use markdown.
"""


def skill_library_text() -> str:
    lines = []
    for name in sorted(DEFAULT_SKILLS):
        skill = DEFAULT_SKILLS[name]
        lines.append(f"- {skill.name}: {skill.summary} Failure types: {', '.join(skill.failure_types)}")
    return "\n".join(lines)


def strict_output_contract() -> str:
    keys = ", ".join(REQUIRED_ACTION_KEYS)
    return (
        "Return exactly these keys with no extras: "
        f"{keys}. "
        "decision must be one of retry, submit, discard. "
        "All array fields must be arrays of strings. "
        "skills_to_call must use only names from the skill library."
    )


def build_teacher_messages(
    *,
    diagnostic: dict[str, Any],
    normalized_diagnostic: dict[str, Any],
    first_attempt_prompt: str | None = None,
) -> list[dict[str, str]]:
    """Build OpenAI-compatible messages for the teacher call."""

    prompt = first_attempt_prompt or str(diagnostic.get("prompt", ""))
    user_payload = {
        "original_prompt": diagnostic.get("prompt", ""),
        "first_attempt_prompt": prompt,
        "expected_constraints": diagnostic.get("expected", {}),
        "geneval_diagnostic": diagnostic,
        "normalized_diagnostic": normalized_diagnostic,
        "skill_library": skill_library_text(),
        "output_contract": strict_output_contract(),
        "example_shape": {
            "decision": "retry",
            "failure_types": ["count_mismatch"],
            "skills_to_call": ["quantity_counting"],
            "preserve_constraints": ["Keep the apples red."],
            "repair_constraints": ["Render exactly three apples."],
            "repair_strategy": "Preserve colors and repair only the count.",
            "retry_prompt": "Exactly three separate red apples on a blue plate.",
            "expected_improvement": ["The retry should satisfy the count check."],
            "regression_risks": ["The retry might change already-correct colors."],
        },
    }
    return [
        {"role": "system", "content": TEACHER_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, indent=2, sort_keys=True)},
    ]
