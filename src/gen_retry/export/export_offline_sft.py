"""Export offline candidate-level retry trajectories to SFT JSONL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gen_retry.prompts.retry_replan_prompt import RETRY_REPLAN_SYSTEM_PROMPT
from gen_retry.schemas.actions import ALLOWED_SKILLS, RetryReplanAction
from gen_retry.utils.io import read_json, write_jsonl


DROP_ALWAYS = {
    "b64_json",
    "base64",
    "image_base64",
    "image_bytes",
    "image_data",
    "image_url",
    "input_image",
    "raw",
    "raw_report",
}
DROP_IMAGE_REFS = {
    "best_so_far_image_path",
    "image_id",
    "image_path",
    "package_path",
    "raw_eval_path",
    "trajectory_path",
}


def export_offline_retry_sft(
    input_dir: str | Path,
    output: str | Path,
    *,
    rejected_output: str | Path | None = None,
    include_image_refs: bool = False,
) -> int:
    """Write step-level retry_replan SFT rows from offline raw trajectories."""

    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for path in sorted(Path(input_dir).glob("*.json")):
        trajectory = read_json(path)
        row, reason = offline_trajectory_to_retry_sft_row(
            trajectory,
            source_path=path,
            include_image_refs=include_image_refs,
        )
        if row is None:
            rejected.append(
                {
                    "trajectory_path": str(path),
                    "trajectory_id": str(trajectory.get("trajectory_id", "")),
                    "candidate_id": str(trajectory.get("candidate_id", "")),
                    "reason": reason,
                }
            )
        else:
            rows.append(row)
    if rejected_output:
        write_jsonl(rejected_output, rejected)
    return write_jsonl(output, rows)


def offline_trajectory_to_retry_sft_row(
    trajectory: dict[str, Any],
    *,
    source_path: str | Path = "",
    include_image_refs: bool = False,
) -> tuple[dict[str, Any] | None, str]:
    action_payload = _retry_action_payload(trajectory)
    if not isinstance(action_payload, dict) or not action_payload:
        return None, "missing_retry_ready_action"
    try:
        action = RetryReplanAction.from_dict(action_payload)
    except Exception as exc:  # noqa: BLE001 - invalid rows should be auditable.
        return None, f"invalid_retry_ready_action: {exc}"

    request = _teacher_request(trajectory)
    if not request:
        request = _fallback_teacher_request(trajectory)
    if not request:
        return None, "missing_teacher_request"

    state = sanitize_sft_state(request, include_image_refs=include_image_refs)
    return (
        {
            "messages": [
                {"role": "system", "content": RETRY_REPLAN_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(state, ensure_ascii=False, sort_keys=True)},
                {
                    "role": "assistant",
                    "content": json.dumps(action.to_dict(), ensure_ascii=False, sort_keys=True),
                },
            ],
            "metadata": {
                "trajectory_id": str(trajectory.get("trajectory_id", "")),
                "prompt_id": str(trajectory.get("prompt_id", "")),
                "candidate_id": str(trajectory.get("candidate_id", "")),
                "sample_type": "retry_replan",
                "source_format": "offline_candidate_trajectory",
                "source_path": str(source_path),
                "round": int(state.get("current_round", state.get("retry_round", 0)) or 0),
                "target_action_type": "retry_replan",
                "image_refs_included": bool(include_image_refs),
            },
        },
        "",
    )


def sanitize_sft_state(value: Any, *, include_image_refs: bool = False) -> Any:
    """Remove raw evaluator payloads and local image artifacts from training input."""

    drop_keys = DROP_ALWAYS | (set() if include_image_refs else DROP_IMAGE_REFS)
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in drop_keys:
                continue
            cleaned[key_text] = sanitize_sft_state(item, include_image_refs=include_image_refs)
        return cleaned
    if isinstance(value, list):
        return [sanitize_sft_state(item, include_image_refs=include_image_refs) for item in value]
    return value


def _retry_action_payload(trajectory: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("retry_ready_action", "latest_teacher_action"):
        value = trajectory.get(key)
        if isinstance(value, dict) and value:
            return dict(value)
    return None


def _teacher_request(trajectory: dict[str, Any]) -> dict[str, Any]:
    value = trajectory.get("latest_teacher_request")
    if isinstance(value, dict) and value:
        return dict(value)
    for attempt in sorted(
        [item for item in trajectory.get("attempts", []) if isinstance(item, dict)],
        key=lambda item: int(item.get("round", 0)),
        reverse=True,
    ):
        value = attempt.get("teacher_request")
        if isinstance(value, dict) and value:
            return dict(value)
    return {}


def _fallback_teacher_request(trajectory: dict[str, Any]) -> dict[str, Any]:
    attempts = sorted(
        [item for item in trajectory.get("attempts", []) if isinstance(item, dict)],
        key=lambda item: int(item.get("round", 0)),
    )
    if not attempts:
        return {}
    current = attempts[-1]
    source = dict(trajectory.get("source") or {})
    memory = dict(trajectory.get("memory") or {})
    evaluation = dict(current.get("evaluation") or {})
    previous_action = dict(memory.get("previous_action") or current.get("previous_action") or current.get("planner_action") or {})
    best_so_far = {
        "round": memory.get("best_so_far_round", 0),
        "score": memory.get("best_so_far_score", 0.0),
        "prompt": memory.get("best_so_far_prompt", ""),
        "failed_constraints": memory.get("best_so_far_failed_constraints", []),
    }
    return {
        "trajectory_id": str(trajectory.get("trajectory_id", "")),
        "prompt_id": str(trajectory.get("prompt_id", "")),
        "candidate_id": str(trajectory.get("candidate_id", "")),
        "original_prompt": str(source.get("original_prompt", "")),
        "prompt_metadata": {
            "skills": source.get("skills", []),
            "atom_count": source.get("atom_count"),
            "vqa_list": source.get("vqa_list", []),
        },
        "previous_initial_plan": dict(trajectory.get("initial_plan") or {}),
        "previous_action": previous_action,
        "previous_prompt": str((current.get("generation") or {}).get("prompt_used", "")),
        "current_round": int(current.get("round", 0)),
        "retry_round": int(current.get("round", 0)) + 1,
        "retry_budget_left": 0,
        "current_eval_report": _without_raw_eval(evaluation),
        "normalized_eval_report": _without_raw_eval(evaluation),
        "memory": {
            "best_so_far": best_so_far,
            "fixed_constraints": memory.get("fixed_constraints", []),
            "persistent_failures": memory.get("persistent_failures", []),
            "new_failures": memory.get("new_failures", []),
            "regressed_constraints": memory.get("regressed_constraints", []),
            "score_delta_from_previous": memory.get("score_delta_from_previous"),
            "score_delta_from_best": memory.get("score_delta_from_best", 0.0),
        },
        "best_so_far": best_so_far,
        "available_skills": sorted(ALLOWED_SKILLS),
    }


def _without_raw_eval(evaluation: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in evaluation.items()
        if key not in {"raw", "raw_report", "raw_eval_path"}
    }
