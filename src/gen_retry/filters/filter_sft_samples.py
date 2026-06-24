"""Filtering rules for planner SFT samples."""

from __future__ import annotations

from typing import Any

from gen_retry.schemas.actions import ALLOWED_SKILLS
from gen_retry.schemas.episode import Episode


ACCEPT_FINAL_OUTCOMES = {"passed_after_retry", "improved_after_retry"}


def should_export_retry_sample(episode: Episode, attempt_index: int) -> tuple[bool, str]:
    if attempt_index <= 0 or attempt_index >= len(episode.attempts):
        return False, "not_retry_attempt"
    attempt = episode.attempts[attempt_index]
    action = attempt.planner_action
    if action is None:
        return False, "missing_retry_action"
    payload = action.to_dict()
    if payload.get("action_type") != "retry_replan":
        return False, "not_retry_replan"
    if payload.get("decision") != "regenerate":
        return False, "decision_not_regenerate"
    if not str(payload.get("retry_prompt", "")).strip():
        return False, "missing_retry_prompt"
    if _has_direct_edit(payload):
        return False, "direct_image_edit_action"
    new_skills = set(payload.get("skill_revision", {}).get("new_skills", []))
    if new_skills - ALLOWED_SKILLS:
        return False, "invalid_skill"
    if not _failure_type_consistent(payload):
        return False, "retry_action_inconsistent_with_failure_type"
    transition = str(attempt.metadata.get("transition_outcome", ""))
    score_delta = float(attempt.metadata.get("score_delta", 0.0))
    failed_delta = int(attempt.metadata.get("failed_constraints_delta", 0))
    new_critical = attempt.metadata.get("new_critical_failures") or []
    if episode.final_outcome == "passed_after_retry":
        return True, "passed_after_retry"
    if episode.final_outcome == "improved_after_retry" and score_delta > 0 and failed_delta < 0:
        return True, "improved_after_retry"
    if episode.final_outcome == "failed_after_budget":
        improved_once = any(
            item.metadata.get("transition_outcome") == "improved_after_retry"
            for item in episode.attempts[1:]
        )
        if improved_once and not new_critical:
            return True, "failed_after_budget_with_improvement"
    if transition == "regressed":
        return False, "regressed"
    if transition == "no_improvement":
        return False, "no_improvement"
    return False, f"final_outcome_excluded:{episode.final_outcome}"


def rejection_record(episode: Episode, attempt_index: int, reason: str) -> dict[str, Any]:
    attempt = episode.attempts[attempt_index]
    return {
        "episode_id": episode.episode_id,
        "sample_type": "retry_replan",
        "round": attempt.round,
        "final_outcome": episode.final_outcome,
        "reason": reason,
    }


def _failure_type_consistent(payload: dict[str, Any]) -> bool:
    failure_types = set(payload.get("failure_types") or [])
    repairs = " ".join(payload.get("repair_constraints") or [])
    diagnosis = str(payload.get("diagnosis", ""))
    if not failure_types:
        return False
    text = (repairs + " " + diagnosis).lower()
    return any(item.lower() in text or item.split("_")[0].lower() in text for item in failure_types)


def _has_direct_edit(value: Any) -> bool:
    blocked = {"image_edit", "edit_instruction", "mask", "bbox", "inpaint", "source_image"}
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in blocked:
                return True
            if _has_direct_edit(item):
                return True
    elif isinstance(value, list):
        return any(_has_direct_edit(item) for item in value)
    return False
