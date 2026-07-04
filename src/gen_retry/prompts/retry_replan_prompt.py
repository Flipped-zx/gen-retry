"""Prompt template for verifier-guided retry re-planning."""

from __future__ import annotations

import json
from typing import Any

from gen_retry.schemas.actions import ALLOWED_SKILLS


RETRY_REPLAN_SYSTEM_PROMPT = """You are a verifier-guided image generation re-planning agent.
Return exactly one JSON object and nothing else. Do not use markdown fences,
comments, prose explanations, or keys outside the requested schema.
Retry means regeneration from a new prompt, not direct image edit.
Use the normalized Geneval/Geneval2 feedback to diagnose failed constraints,
explain weakness in the previous plan/prompt/skill usage, revise skills if needed,
and produce a new retry_prompt for regeneration.
The decision must be "regenerate" whenever a retry is requested.
If the report already passes, do not produce retry_replan.
Do not use web search, image search, reference image retrieval, masks, bounding
boxes, source-image edits, inpainting fields, or any direct image edit action.
Skill names must come from the fixed skill library.
Do not invent objects, colors, counts, attributes, actions, or spatial relations
that are not in the original prompt. Repair only the verifier-failed constraints
while carrying forward constraints that already passed.
preserve_constraints means previously passed semantic constraints to explicitly
carry into the new prompt; it does not mean pixel-level preservation.
Use previous_action to reason about what the last retry tried. Use the memory
diff fields to distinguish fixed constraints, persistent failures, new failures,
and regressed constraints. Set branch_source to "latest" if the next retry
should build from the latest attempt, or "best_so_far" if a regression means the
next retry should branch from the strongest earlier attempt.
Quality bar:
- Translate every failed constraint into a concrete repair clause.
- Translate passed constraints into explicit preservation clauses when they
  could regress during regeneration.
- For count failures, state the exact count, make instances visually separable,
  and add negative clauses against extras or duplicates.
- For attribute or color failures, bind the attribute to the specific target
  object; do not apply the attribute globally.
- For spatial or relation failures, write the subject, relation, and object in
  an unambiguous layout clause.
- For persistent failures, change strategy instead of repeating the previous
  prompt with minor wording changes.
The teacher does not need raw image bytes. Image paths in history are artifact
references only; reason from the normalized evaluator report and trajectory
memory.
The retry_prompt must be directly usable by a text-to-image generator.
"""


def build_retry_replan_messages(
    *,
    original_prompt: str,
    previous_initial_plan: dict[str, Any],
    previous_action: dict[str, Any] | None = None,
    previous_prompt: str,
    previous_selected_skills: list[str],
    normalized_eval_report: dict[str, Any],
    retry_history: list[dict[str, Any]],
    retry_budget_left: int,
    current_round: int = 0,
    best_so_far: dict[str, Any] | None = None,
    fixed_constraints: list[Any] | None = None,
    persistent_failures: list[Any] | None = None,
    new_failures: list[Any] | None = None,
    regressed_constraints: list[Any] | None = None,
    score_delta_from_previous: Any = 0.0,
    score_delta_from_best: Any = 0.0,
    branch_source: str = "latest",
    branch_source_round: int = 0,
    available_skills: Any = None,
) -> list[dict[str, str]]:
    best = dict(best_so_far or {})
    memory = {
        "best_so_far": best,
        "fixed_constraints": list(fixed_constraints or []),
        "persistent_failures": list(persistent_failures or []),
        "new_failures": list(new_failures or []),
        "regressed_constraints": list(regressed_constraints or []),
        "score_delta_from_previous": _nullable_float(score_delta_from_previous),
        "score_delta_from_best": _nullable_float(score_delta_from_best),
    }
    state = {
        "original_prompt": original_prompt,
        "previous_initial_plan": previous_initial_plan,
        "previous_action": dict(previous_action or {}),
        "previous_prompt": previous_prompt,
        "previous_selected_skills": previous_selected_skills,
        "current_round": int(current_round),
        "current_eval_report": normalized_eval_report,
        "normalized_eval_report": normalized_eval_report,
        "retry_history": retry_history,
        "memory": memory,
        "best_so_far": best,
        "fixed_constraints": list(fixed_constraints or []),
        "persistent_failures": list(persistent_failures or []),
        "new_failures": list(new_failures or []),
        "regressed_constraints": list(regressed_constraints or []),
        "score_delta_from_previous": _nullable_float(score_delta_from_previous),
        "score_delta_from_best": _nullable_float(score_delta_from_best),
        "branch_source": branch_source,
        "branch_source_round": int(branch_source_round),
        "retry_budget_left": retry_budget_left,
        "available_skills": available_skills or sorted(ALLOWED_SKILLS),
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
            "branch_source_round": 0,
            "branch_source": "latest|best_so_far",
        },
    }
    return [
        {"role": "system", "content": RETRY_REPLAN_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)},
    ]


def _nullable_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
