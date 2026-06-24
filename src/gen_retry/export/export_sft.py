"""Export regeneration-planner episodes to ShareGPT SFT JSONL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gen_retry.filters.filter_sft_samples import rejection_record, should_export_retry_sample
from gen_retry.prompts.initial_plan_prompt import INITIAL_PLAN_SYSTEM_PROMPT
from gen_retry.prompts.retry_replan_prompt import RETRY_REPLAN_SYSTEM_PROMPT
from gen_retry.schemas.episode import Episode
from gen_retry.utils.io import read_json, write_jsonl


def export_episode_sft(
    input_dir: str | Path,
    output: str | Path,
    *,
    rejected_output: str | Path = "data/rejected/retry_replan_rejected.jsonl",
    views: tuple[str, ...] = ("initial_plan_sft", "retry_replan_sft"),
) -> int:
    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for path in sorted(Path(input_dir).glob("*.json")):
        episode = Episode.from_dict(read_json(path))
        if "initial_plan_sft" in views:
            rows.append(_initial_plan_row(episode))
        if "retry_replan_sft" in views:
            for index in range(1, len(episode.attempts)):
                include, reason = should_export_retry_sample(episode, index)
                if include:
                    rows.append(_retry_replan_row(episode, index))
                else:
                    rejected.append(rejection_record(episode, index, reason))
    write_jsonl(rejected_output, rejected)
    return write_jsonl(output, rows)


def _initial_plan_row(episode: Episode) -> dict[str, Any]:
    state = {
        "original_prompt": episode.original_prompt,
        "evaluator_type": episode.evaluator_type,
    }
    return {
        "messages": [
            {"role": "system", "content": INITIAL_PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(state, ensure_ascii=False, sort_keys=True)},
            {
                "role": "assistant",
                "content": json.dumps(episode.initial_plan.to_dict(), ensure_ascii=False, sort_keys=True),
            },
        ],
        "metadata": {
            "episode_id": episode.episode_id,
            "sample_type": "initial_plan",
            "round": 0,
            "final_outcome": episode.final_outcome,
        },
    }


def _retry_replan_row(episode: Episode, attempt_index: int) -> dict[str, Any]:
    attempt = episode.attempts[attempt_index]
    previous = episode.attempts[attempt_index - 1]
    action = attempt.planner_action
    state = {
        "original_prompt": episode.original_prompt,
        "previous_initial_plan": episode.initial_plan.to_dict(),
        "previous_prompt": previous.prompt_used,
        "previous_selected_skills": _previous_selected_skills(episode, attempt_index),
        "normalized_eval_report": _report_without_raw(previous.eval_report.to_dict()),
        "retry_history": _retry_history_for_export(episode, attempt_index),
        "retry_budget_left": previous.metadata.get("retry_budget_left", 0),
    }
    return {
        "messages": [
            {"role": "system", "content": RETRY_REPLAN_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(state, ensure_ascii=False, sort_keys=True)},
            {
                "role": "assistant",
                "content": json.dumps(action.to_dict(), ensure_ascii=False, sort_keys=True) if action else "{}",
            },
        ],
        "metadata": {
            "episode_id": episode.episode_id,
            "sample_type": "retry_replan",
            "round": attempt.round,
            "final_outcome": episode.final_outcome,
        },
    }


def _previous_selected_skills(episode: Episode, attempt_index: int) -> list[str]:
    if attempt_index <= 1:
        return list(episode.initial_plan.selected_skills)
    previous_action = episode.attempts[attempt_index - 1].planner_action
    if previous_action and previous_action.action_type == "retry_replan":
        return [
            str(item)
            for item in previous_action.to_dict().get("skill_revision", {}).get("new_skills", [])
            if str(item).strip()
        ]
    return list(episode.initial_plan.selected_skills)


def _retry_history_for_export(episode: Episode, stop_index: int) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for attempt in episode.attempts[:stop_index]:
        history.append(
            {
                "round": attempt.round,
                "prompt_used": attempt.prompt_used,
                "score": attempt.eval_report.score,
                "failed_constraints": [
                    item.to_dict() for item in attempt.eval_report.failed_constraints
                ],
                "transition_outcome": attempt.metadata.get("transition_outcome"),
            }
        )
    return history


def _report_without_raw(report: dict[str, Any]) -> dict[str, Any]:
    report = dict(report)
    report.pop("raw_report", None)
    return report
