"""Export raw retry episodes into policy-only ShareGPT SFT rows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gen_retry.schemas.episode_schema import Episode
from gen_retry.utils.io import read_json, write_jsonl


SYSTEM_PROMPT = (
    "You are a diagnostic visual retry agent. Given the original prompt, current "
    "Geneval report, history summary, and retry budget, output the next teacher "
    "action as strict JSON. Preserve passed constraints and repair failed constraints."
)


def export_policy_sft(
    episodes_dir: str | Path = "data/raw_episodes",
    output: str | Path = "data/sft/retry_policy_sft_sharegpt.jsonl",
    *,
    include_partial: bool = False,
    include_negative: bool = False,
) -> int:
    rows: list[dict[str, Any]] = []
    for path in sorted(Path(episodes_dir).glob("*.json")):
        episode = Episode.from_dict(read_json(path))
        rows.extend(
            _episode_rows(
                episode,
                include_partial=include_partial,
                include_negative=include_negative,
            )
        )
    return write_jsonl(output, rows)


def _episode_rows(
    episode: Episode,
    *,
    include_partial: bool,
    include_negative: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, attempt in enumerate(episode.attempts):
        action = attempt.teacher_action
        if action is None:
            continue
        transition = str(attempt.metadata.get("transition_outcome", ""))
        new_critical = bool(attempt.metadata.get("new_critical_failures", False))
        if not _include_action(
            episode.final_outcome,
            transition,
            action.decision,
            new_critical,
            include_partial=include_partial,
            include_negative=include_negative,
        ):
            continue
        state = {
            "original_prompt": episode.original_prompt,
            "current_geneval_report": attempt.geneval_report.to_dict(),
            "history_summary": _history_summary(episode, stop_index=index),
            "retry_budget_left": attempt.metadata.get("retry_budget_left", 0),
        }
        rows.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(state, ensure_ascii=False, sort_keys=True)},
                    {
                        "role": "assistant",
                        "content": json.dumps(action.to_dict(), ensure_ascii=False, sort_keys=True),
                    },
                ],
                "metadata": {
                    "episode_id": episode.id,
                    "round": attempt.round,
                    "final_outcome": episode.final_outcome,
                    "transition_outcome": transition,
                },
            }
        )
    return rows


def _include_action(
    final_outcome: str,
    transition: str,
    decision: str,
    new_critical: bool,
    *,
    include_partial: bool,
    include_negative: bool,
) -> bool:
    if include_negative:
        return True
    if transition == "passed_after_retry":
        return True
    if transition == "partial_improved" and not new_critical:
        return True
    if include_partial and transition == "partial_improved":
        return True
    if final_outcome == "pass_without_retry" and decision == "submit":
        return True
    return False


def _history_summary(episode: Episode, *, stop_index: int) -> str:
    parts: list[str] = []
    for attempt in episode.attempts[: stop_index + 1]:
        failed = [item.type for item in attempt.geneval_report.failed_constraints]
        parts.append(
            f"round={attempt.round} type={attempt.attempt_type} "
            f"score={attempt.geneval_report.score:.3f} failed={failed}"
        )
    return " | ".join(parts)

