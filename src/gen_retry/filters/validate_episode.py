"""Validation for visual retry episode JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gen_retry.schemas.episode_schema import (
    ACTION_TYPES,
    ATTEMPT_TYPES,
    TEACHER_DECISIONS,
    Episode,
)


VALID_FINAL_OUTCOMES = {
    "pass_without_retry",
    "passed_after_retry",
    "teacher_submit",
    "invalid_submit",
    "abandon",
    "failed_after_budget",
}


def validate_episode(episode: Episode, *, mock_mode: bool = True) -> list[str]:
    errors: list[str] = []
    if not episode.id:
        errors.append("episode.id is required")
    if not episode.original_prompt:
        errors.append("episode.original_prompt is required")
    if not episode.attempts:
        errors.append("episode.attempts must be non-empty")
    if episode.final_outcome not in VALID_FINAL_OUTCOMES:
        errors.append(f"invalid final_outcome: {episode.final_outcome}")

    for index, attempt in enumerate(episode.attempts):
        prefix = f"attempt[{index}]"
        if attempt.round < 0:
            errors.append(f"{prefix}.round must be non-negative")
        if attempt.attempt_type not in ATTEMPT_TYPES:
            errors.append(f"{prefix}.attempt_type is invalid: {attempt.attempt_type}")
        if not attempt.prompt:
            errors.append(f"{prefix}.prompt is required")
        if not attempt.image_path:
            errors.append(f"{prefix}.image_path is required")
        elif not mock_mode and not Path(attempt.image_path).exists():
            errors.append(f"{prefix}.image_path does not exist: {attempt.image_path}")
        if not (0.0 <= attempt.geneval_report.score <= 1.0):
            errors.append(f"{prefix}.geneval_report.score must be between 0 and 1")
        action = attempt.teacher_action
        if action is None:
            continue
        if action.decision not in TEACHER_DECISIONS:
            errors.append(f"{prefix}.teacher_action.decision is invalid: {action.decision}")
        if action.action_type not in ACTION_TYPES:
            errors.append(f"{prefix}.teacher_action.action_type is invalid: {action.action_type}")
        if not attempt.geneval_report.failed_constraints and action.decision != "submit":
            errors.append(f"{prefix}.teacher_action should usually submit when no constraints failed")
        if action.decision == "retry" and not action.edit_instruction and not action.retry_prompt:
            errors.append(f"{prefix}.teacher_action retry requires edit_instruction or retry_prompt")
    return errors


def validate_episode_dict(data: dict[str, Any], *, mock_mode: bool = True) -> list[str]:
    return validate_episode(Episode.from_dict(data), mock_mode=mock_mode)
