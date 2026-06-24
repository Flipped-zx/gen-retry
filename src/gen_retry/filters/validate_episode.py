"""Validation for new regeneration-only episodes and legacy retry episodes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gen_retry.schemas.actions import ALLOWED_SKILLS, ActionValidationError, RetryReplanAction
from gen_retry.schemas.episode import EVALUATOR_TYPES, FINAL_OUTCOMES, Episode
from gen_retry.schemas.episode_schema import (
    ACTION_TYPES,
    ATTEMPT_TYPES,
    TEACHER_DECISIONS,
    Episode as LegacyEpisode,
)


def validate_episode(episode: Any, *, mock_mode: bool = True) -> list[str]:
    if hasattr(episode, "episode_id"):
        return validate_planner_episode(episode, mock_mode=mock_mode)
    return validate_legacy_episode(episode, mock_mode=mock_mode)


def validate_episode_dict(data: dict[str, Any], *, mock_mode: bool = True) -> list[str]:
    if "episode_id" in data:
        try:
            episode = Episode.from_dict(data)
        except Exception as exc:  # noqa: BLE001
            return [f"schema error: {exc}"]
        return validate_planner_episode(episode, mock_mode=mock_mode)
    return validate_legacy_episode(LegacyEpisode.from_dict(data), mock_mode=mock_mode)


def validate_planner_episode(episode: Episode, *, mock_mode: bool = True) -> list[str]:
    errors: list[str] = []
    if not episode.episode_id:
        errors.append("episode_id is required")
    if not episode.original_prompt:
        errors.append("original_prompt is required")
    if episode.evaluator_type not in EVALUATOR_TYPES:
        errors.append(f"invalid evaluator_type: {episode.evaluator_type}")
    if episode.final_outcome not in FINAL_OUTCOMES:
        errors.append(f"invalid final_outcome: {episode.final_outcome}")
    try:
        episode.initial_plan.validate()
    except ActionValidationError as exc:
        errors.append(f"initial_plan invalid: {exc}")
    if not episode.attempts:
        errors.append("attempts must be non-empty")

    for index, attempt in enumerate(episode.attempts):
        prefix = f"attempt[{index}]"
        if attempt.round != index:
            errors.append(f"{prefix}.round should equal its attempt index")
        if not attempt.prompt_used:
            errors.append(f"{prefix}.prompt_used is required")
        if not attempt.image_path:
            errors.append(f"{prefix}.image_path is required")
        elif not mock_mode and not Path(attempt.image_path).exists():
            errors.append(f"{prefix}.image_path does not exist: {attempt.image_path}")
        score = attempt.eval_report.score
        if not (0.0 <= score <= 1.0):
            errors.append(f"{prefix}.eval_report.score must be between 0 and 1")
        if attempt.planner_action is None:
            errors.append(f"{prefix}.planner_action is required")
            continue
        action_payload = attempt.planner_action.to_dict()
        direct_keys = _direct_image_edit_keys(action_payload)
        if direct_keys:
            errors.append(f"{prefix}.planner_action contains direct image edit fields: {direct_keys}")
        if index == 0 and action_payload.get("action_type") != "initial_plan":
            errors.append(f"{prefix}.planner_action must be initial_plan")
        if index > 0:
            if action_payload.get("action_type") != "retry_replan":
                errors.append(f"{prefix}.planner_action must be retry_replan")
            else:
                try:
                    RetryReplanAction.from_dict(action_payload)
                except ActionValidationError as exc:
                    errors.append(f"{prefix}.retry_replan invalid: {exc}")
                if action_payload.get("decision") != "regenerate":
                    errors.append(f"{prefix}.retry_replan.decision must be regenerate")
                if not action_payload.get("retry_prompt"):
                    errors.append(f"{prefix}.retry_replan.retry_prompt is required")
                skills = set(action_payload.get("skill_revision", {}).get("new_skills", []))
                invalid = sorted(skills - ALLOWED_SKILLS)
                if invalid:
                    errors.append(f"{prefix}.retry_replan uses invalid skills: {invalid}")
    return errors


def validate_legacy_episode(episode: LegacyEpisode, *, mock_mode: bool = True) -> list[str]:
    errors: list[str] = []
    if not episode.id:
        errors.append("episode.id is required")
    if not episode.original_prompt:
        errors.append("episode.original_prompt is required")
    if not episode.attempts:
        errors.append("episode.attempts must be non-empty")
    if episode.final_outcome not in {
        "pass_without_retry",
        "passed_after_retry",
        "teacher_submit",
        "invalid_submit",
        "abandon",
        "failed_after_budget",
    }:
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


def _direct_image_edit_keys(value: Any) -> list[str]:
    blocked = {"image_edit", "edit_instruction", "mask", "bbox", "inpaint", "source_image"}
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in blocked:
                found.add(str(key))
            found.update(_direct_image_edit_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_direct_image_edit_keys(item))
    return sorted(found)
