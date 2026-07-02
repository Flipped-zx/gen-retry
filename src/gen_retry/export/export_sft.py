"""Export regeneration-planner episodes to ShareGPT SFT JSONL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gen_retry.filters.filter_sft_samples import rejection_record, should_export_retry_sample
from gen_retry.prompts.initial_plan_prompt import INITIAL_PLAN_SYSTEM_PROMPT
from gen_retry.prompts.retry_replan_prompt import RETRY_REPLAN_SYSTEM_PROMPT
from gen_retry.schemas.episode import Episode
from gen_retry.skills.skill_library import ALLOWED_SKILLS, query_skill
from gen_retry.utils.io import read_json, write_jsonl


RAW_EPISODE_EXPORT_FORMATS = {"compact", "tool", "both"}

TOOL_TRAJECTORY_SYSTEM_PROMPT = """You are a Gen-Retry planner/controller.
Use only the allowed tools: query_skill, generate_image, judge_image.
Retry means re-planning and regeneration from a new prompt, not direct image edit.
Do not use search, image_search, browse, masks, bounding boxes, inpainting, or direct image editing.
Assistant messages are trainable controller actions. Tool responses are context only.
"""


def export_episode_sft(
    input_dir: str | Path,
    output: str | Path,
    *,
    rejected_output: str | Path = "data/rejected/retry_replan_rejected.jsonl",
    views: tuple[str, ...] = ("initial_plan_sft", "retry_replan_sft"),
    export_format: str = "compact",
    tool_output: str | Path | None = None,
) -> int:
    if export_format not in RAW_EPISODE_EXPORT_FORMATS:
        raise ValueError(f"unsupported raw episode export format: {export_format}")
    if export_format == "tool":
        return export_episode_tool_sft(input_dir, output)
    if export_format == "both":
        written = _export_episode_compact_sft(input_dir, output, rejected_output=rejected_output, views=views)
        export_episode_tool_sft(input_dir, tool_output or _default_tool_output(output))
        return written
    return _export_episode_compact_sft(input_dir, output, rejected_output=rejected_output, views=views)


def _export_episode_compact_sft(
    input_dir: str | Path,
    output: str | Path,
    *,
    rejected_output: str | Path,
    views: tuple[str, ...],
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


def export_episode_tool_sft(input_dir: str | Path, output: str | Path) -> int:
    rows: list[dict[str, Any]] = []
    for path in sorted(Path(input_dir).glob("*.json")):
        episode = Episode.from_dict(read_json(path))
        row = _tool_trajectory_row(episode)
        errors = validate_tool_trajectory_row(row)
        if errors:
            raise ValueError(f"{path} produced invalid tool trajectory: {errors}")
        rows.append(row)
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
    memory = _memory_for_export(episode, attempt_index - 1)
    state = {
        "original_prompt": episode.original_prompt,
        "current_round": attempt.round,
        "previous_initial_plan": episode.initial_plan.to_dict(),
        "previous_action": previous.planner_action.to_dict() if previous.planner_action else {},
        "previous_prompt": previous.prompt_used,
        "previous_selected_skills": _previous_selected_skills(episode, attempt_index),
        "current_eval_report": _report_without_raw(previous.eval_report.to_dict()),
        "normalized_eval_report": _report_without_raw(previous.eval_report.to_dict()),
        "retry_history": _retry_history_for_export(episode, attempt_index),
        "memory": memory,
        "best_so_far": memory["best_so_far"],
        "fixed_constraints": memory["fixed_constraints"],
        "persistent_failures": memory["persistent_failures"],
        "new_failures": memory["new_failures"],
        "regressed_constraints": memory["regressed_constraints"],
        "score_delta_from_previous": memory["score_delta_from_previous"],
        "score_delta_from_best": memory["score_delta_from_best"],
        "retry_budget_left": previous.metadata.get("retry_budget_left", 0),
        "available_skills": sorted(ALLOWED_SKILLS),
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


def _tool_trajectory_row(episode: Episode) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    trainable: list[int] = []
    non_trainable: list[int] = []

    def add(role: str, content: str, *, is_trainable: bool = False) -> None:
        index = len(messages)
        messages.append({"role": role, "content": content})
        if is_trainable:
            trainable.append(index)
        else:
            non_trainable.append(index)

    add("system", TOOL_TRAJECTORY_SYSTEM_PROMPT)
    add("user", f"<user>\n{episode.original_prompt}\n</user>")
    add("assistant", _tagged_json("plan", episode.initial_plan.to_dict()), is_trainable=True)

    for skill_name in _valid_skills(episode.initial_plan.selected_skills):
        _add_tool_call(add, "query_skill", {"skill_name": skill_name})
        _add_tool_response(add, {"name": "query_skill", "result": query_skill(skill_name)})

    if episode.attempts:
        first = episode.attempts[0]
        _add_tool_call(add, "generate_image", {"attempt": "initial", "prompt": first.prompt_used})
        _add_tool_response(add, {"image_ref": _attempt_ref(first.round)})
        _add_tool_call(add, "judge_image", {"evaluator": "geneval2", "image_ref": _attempt_ref(first.round)})
        _add_tool_response(add, _tool_eval_response(first))

    for attempt_index in range(1, len(episode.attempts)):
        previous = episode.attempts[attempt_index - 1]
        attempt = episode.attempts[attempt_index]
        action = attempt.planner_action
        action_data = action.to_dict() if action else {}
        add(
            "assistant",
            _tagged_json("diagnose", _diagnosis_payload(previous, action_data)),
            is_trainable=True,
        )
        add("assistant", _tagged_json("retry_replan", action_data), is_trainable=True)
        for skill_name in _valid_skills(action_data.get("skill_revision", {}).get("new_skills", [])):
            _add_tool_call(add, "query_skill", {"skill_name": skill_name})
            _add_tool_response(add, {"name": "query_skill", "result": query_skill(skill_name)})
        _add_tool_call(add, "generate_image", {"attempt": "retry", "prompt": attempt.prompt_used})
        _add_tool_response(add, {"image_ref": _attempt_ref(attempt.round)})
        _add_tool_call(add, "judge_image", {"evaluator": "geneval2", "image_ref": _attempt_ref(attempt.round)})
        _add_tool_response(add, _tool_eval_response(attempt))

    submit = {
        "decision": "submit" if episode.stop_rule_result and episode.stop_rule_result.passed else "stop",
        "final_outcome": episode.final_outcome,
        "stop_reason": episode.stop_rule_result.reason if episode.stop_rule_result else "",
    }
    add("assistant", _tagged_json("submit", submit), is_trainable=True)
    row = {
        "messages": messages,
        "metadata": {
            "episode_id": episode.episode_id,
            "sample_type": "tool_trajectory",
            "format": "tool_trajectory_sharegpt",
            "final_outcome": episode.final_outcome,
            "trainable_message_indices": trainable,
            "non_trainable_message_indices": non_trainable,
            "tool_names": ["query_skill", "generate_image", "judge_image"],
            "tool_response_role": "user",
            "tool_responses_trainable": False,
            "retry_rounds": max(0, len(episode.attempts) - 1),
        },
    }
    return row


def _add_tool_call(add: Any, name: str, arguments: dict[str, Any]) -> None:
    add("assistant", _tagged_json("tool_call", {"name": name, "arguments": arguments}), is_trainable=True)


def _add_tool_response(add: Any, payload: dict[str, Any]) -> None:
    add("user", _tagged_json("tool_response", payload))


def _tool_eval_response(attempt: Any) -> dict[str, Any]:
    return {
        "image_ref": _attempt_ref(attempt.round),
        "normalized_eval_report": _report_without_raw(attempt.eval_report.to_dict()),
    }


def _diagnosis_payload(previous_attempt: Any, action_data: dict[str, Any]) -> dict[str, Any]:
    report = _report_without_raw(previous_attempt.eval_report.to_dict())
    return {
        "failed_constraints": report.get("failed_constraints", []),
        "passed_constraints": report.get("passed_constraints", []),
        "failure_types": action_data.get("failure_types", []),
        "diagnosis": action_data.get("diagnosis", ""),
        "previous_plan_error": action_data.get("previous_plan_error", {}),
    }


def _valid_skills(values: Any) -> list[str]:
    out: list[str] = []
    for value in values or []:
        skill_name = str(value).strip()
        if skill_name in ALLOWED_SKILLS and skill_name not in out:
            out.append(skill_name)
    return out


def _tagged_json(tag: str, payload: dict[str, Any]) -> str:
    return f"<{tag}>\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n</{tag}>"


def _attempt_ref(round_index: int) -> str:
    return f"attempt_{round_index}"


def _default_tool_output(output: str | Path) -> Path:
    path = Path(output)
    suffix = path.suffix or ".jsonl"
    return path.with_name(f"{path.stem}_tool{suffix}")


def validate_tool_trajectory_row(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    messages = row.get("messages")
    if not isinstance(messages, list):
        return ["messages must be a list"]
    forbidden_names = {"search", "image_search", "browse"}
    forbidden_json_keys = (
        '"image_edit"',
        '"edit_instruction"',
        '"mask"',
        '"bbox"',
        '"bounding_box"',
        '"bounding_boxes"',
        '"inpaint"',
        '"inpainting"',
    )
    tool_calls: list[tuple[str, dict[str, Any]]] = []
    has_diagnose = False
    has_retry_replan = False
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            errors.append(f"message {index} is not an object")
            continue
        role = message.get("role")
        content = str(message.get("content", ""))
        if role == "assistant":
            lower = content.lower()
            if any(term in lower for term in forbidden_json_keys):
                errors.append(f"assistant message {index} contains a forbidden direct-edit term")
            if content.startswith("<diagnose>"):
                has_diagnose = True
            if content.startswith("<retry_replan>"):
                has_retry_replan = True
                payload = _extract_tagged_json(content, "retry_replan", errors, index)
                if not str(payload.get("retry_prompt", "")).strip():
                    errors.append(f"retry_replan message {index} missing retry_prompt")
            if content.startswith("<tool_call>"):
                payload = _extract_tagged_json(content, "tool_call", errors, index)
                name = str(payload.get("name", ""))
                arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
                tool_calls.append((name, arguments))
                if name in forbidden_names:
                    errors.append(f"forbidden tool call: {name}")
                if name == "query_skill" and arguments.get("skill_name") not in ALLOWED_SKILLS:
                    errors.append(f"invalid query_skill skill: {arguments.get('skill_name')}")
                if name == "generate_image" and not str(arguments.get("prompt", "")).strip():
                    errors.append("generate_image call missing prompt")
                if name == "judge_image" and arguments.get("evaluator") != "geneval2":
                    errors.append("judge_image call must use evaluator geneval2")
    names = [name for name, _ in tool_calls]
    for required in ("query_skill", "generate_image", "judge_image"):
        if required not in names:
            errors.append(f"missing required tool call: {required}")
    for index, name in enumerate(names):
        if name == "generate_image":
            following = names[index + 1 :]
            if "judge_image" not in following:
                errors.append("generate_image is not followed by judge_image")
            elif "generate_image" in following[: following.index("judge_image")]:
                errors.append("generate_image must be judged before another generation")
    retry_rounds = int(row.get("metadata", {}).get("retry_rounds", 0)) if isinstance(row.get("metadata"), dict) else 0
    if retry_rounds > 0 and not (has_diagnose and has_retry_replan):
        errors.append("retry trajectory missing diagnose or retry_replan")
    return errors


def _extract_tagged_json(content: str, tag: str, errors: list[str], index: int) -> dict[str, Any]:
    open_tag = f"<{tag}>"
    close_tag = f"</{tag}>"
    if not content.startswith(open_tag) or not content.rstrip().endswith(close_tag):
        errors.append(f"message {index} has malformed {tag} tag")
        return {}
    body = content[len(open_tag) : content.rfind(close_tag)].strip()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        errors.append(f"message {index} has invalid {tag} JSON: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"message {index} {tag} payload must be an object")
        return {}
    return payload


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
                    _constraint_without_raw(item.to_dict()) for item in attempt.eval_report.failed_constraints
                ],
                "transition_outcome": attempt.metadata.get("transition_outcome"),
            }
        )
    return history


def _memory_for_export(episode: Episode, current_index: int) -> dict[str, Any]:
    attempts = episode.attempts[: current_index + 1]
    current = attempts[-1]
    previous = attempts[-2] if len(attempts) > 1 else None
    best = _best_attempt(attempts)
    transition = _transition_sets(previous, current)
    score_delta_from_previous = (
        current.eval_report.score - previous.eval_report.score if previous else 0.0
    )
    score_delta_from_best = current.eval_report.score - best.eval_report.score if best else 0.0
    return {
        "best_so_far": {
            "round": best.round if best else current.round,
            "score": best.eval_report.score if best else current.eval_report.score,
            "image_ref": _attempt_ref(best.round if best else current.round),
            "prompt": best.prompt_used if best else current.prompt_used,
            "failed_constraints": (
                [_constraint_without_raw(item.to_dict()) for item in best.eval_report.failed_constraints]
                if best
                else []
            ),
        },
        "fixed_constraints": transition["fixed_constraints"],
        "persistent_failures": transition["persistent_failures"],
        "new_failures": transition["new_failures"],
        "regressed_constraints": transition["regressed_constraints"],
        "score_delta_from_previous": score_delta_from_previous,
        "score_delta_from_best": score_delta_from_best,
    }


def _best_attempt(attempts: list[Any]) -> Any | None:
    best = None
    for attempt in attempts:
        if best is None:
            best = attempt
            continue
        if attempt.eval_report.score > best.eval_report.score:
            best = attempt
        elif attempt.eval_report.score == best.eval_report.score and (
            len(attempt.eval_report.failed_constraints) < len(best.eval_report.failed_constraints)
        ):
            best = attempt
    return best


def _transition_sets(previous: Any | None, current: Any) -> dict[str, list[dict[str, Any]]]:
    if previous is None:
        return {
            "fixed_constraints": [],
            "persistent_failures": [],
            "new_failures": [
                _constraint_without_raw(item.to_dict()) for item in current.eval_report.failed_constraints
            ],
            "regressed_constraints": [],
        }
    previous_failed = {_constraint_key(item.to_dict()): item for item in previous.eval_report.failed_constraints}
    previous_passed = {_constraint_key(item.to_dict()): item for item in previous.eval_report.passed_constraints}
    current_failed = {_constraint_key(item.to_dict()): item for item in current.eval_report.failed_constraints}
    current_passed = {_constraint_key(item.to_dict()): item for item in current.eval_report.passed_constraints}
    return {
        "fixed_constraints": [
            _constraint_without_raw(current_passed[key].to_dict())
            for key in sorted(set(previous_failed) & set(current_passed))
        ],
        "persistent_failures": [
            _constraint_without_raw(current_failed[key].to_dict())
            for key in sorted(set(previous_failed) & set(current_failed))
        ],
        "new_failures": [
            _constraint_without_raw(current_failed[key].to_dict())
            for key in sorted(set(current_failed) - set(previous_failed))
        ],
        "regressed_constraints": [
            _constraint_without_raw(current_failed[key].to_dict())
            for key in sorted(set(previous_passed) & set(current_failed))
        ],
    }


def _constraint_key(constraint: dict[str, Any]) -> str:
    return "|".join(
        [
            str(constraint.get("type", "")),
            str(constraint.get("target", "")),
            json.dumps(constraint.get("expected"), ensure_ascii=False, sort_keys=True),
        ]
    )


def _report_without_raw(report: dict[str, Any]) -> dict[str, Any]:
    report = dict(report)
    report.pop("raw_report", None)
    for key in ("passed_constraints", "failed_constraints", "uncertain_constraints"):
        value = report.get(key)
        if isinstance(value, list):
            report[key] = [_constraint_without_raw(item) for item in value if isinstance(item, dict)]
    return report


def _constraint_without_raw(constraint: dict[str, Any]) -> dict[str, Any]:
    cleaned = {
        "type": constraint.get("type"),
        "target": constraint.get("target"),
        "expected": constraint.get("expected"),
        "detected": constraint.get("detected"),
        "status": constraint.get("status"),
    }
    details = constraint.get("details")
    if isinstance(details, dict):
        safe_details = {
            key: value
            for key, value in details.items()
            if key
            not in {
                "raw",
                "image_id",
                "image_path",
                "prompt_id",
                "sample_id",
                "id",
            }
        }
        if safe_details:
            cleaned["details"] = safe_details
    return cleaned
