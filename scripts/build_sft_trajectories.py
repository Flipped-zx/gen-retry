#!/usr/bin/env python3
"""Build SFT trajectories from diagnostics and teacher retry actions."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.data.io import read_json_or_jsonl, write_jsonl
from gen_retry.eval.diagnostic_normalizer import normalize_geneval_diagnostic
from gen_retry.teacher.build_retry_action import extract_diagnostic, record_id
from gen_retry.teacher.schemas import validate_teacher_retry_action
from gen_retry.tools.skills import DEFAULT_SKILLS


SFT_SYSTEM_PROMPT = """You are a Gen-Retry student. Use Geneval diagnostics to preserve passed constraints, repair failed constraints, call the right skill, retry generation, and submit only after improvement."""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Gen-Retry SFT trajectory JSONL.")
    parser.add_argument("--diagnostics", default="data/raw/geneval_diagnostics.jsonl")
    parser.add_argument("--teacher-actions", default="data/processed/teacher_retry_actions.jsonl")
    parser.add_argument("--output", default="data/processed/geneval_retry_sft.jsonl")
    parser.add_argument(
        "--trajectory-format",
        choices=("full", "compact"),
        default="full",
        help="Emit full mocked retry episodes by default, or compact diagnostic-to-action rows.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Compatibility alias for --trajectory-format compact.",
    )
    parser.add_argument(
        "--diagnostic-detail",
        choices=("compact", "raw"),
        default="compact",
        help="Use compact normalized diagnostics in SFT contexts by default; raw keeps full detector outputs in contexts.",
    )
    args = parser.parse_args()
    trajectory_format = "compact" if args.compact else args.trajectory_format

    diagnostics = read_json_or_jsonl(args.diagnostics)
    actions = read_json_or_jsonl(args.teacher_actions)
    diagnostics_by_id = {
        record_id(record, index): extract_diagnostic(record)
        for index, record in enumerate(diagnostics)
    }

    rows = []
    for index, action_row in enumerate(actions):
        row_id = str(action_row.get("id") or f"sample_{index:06d}")
        diagnostic = diagnostics_by_id.get(row_id)
        if not isinstance(diagnostic, dict):
            diagnostic = action_row.get("diagnostic")
        if not isinstance(diagnostic, dict):
            raise ValueError(f"No diagnostic found for teacher action row {row_id}")
        normalized = normalize_geneval_diagnostic(diagnostic)
        action = validate_teacher_retry_action(action_row.get("teacher_retry_action")).to_dict()
        if trajectory_format == "compact":
            rows.append(build_sft_row(row_id, diagnostic, normalized, action))
        else:
            rows.append(
                build_full_episode_sft_row(
                    row_id,
                    diagnostic,
                    normalized,
                    action,
                    retry_diagnostic=_extract_retry_diagnostic(action_row),
                    diagnostic_detail=args.diagnostic_detail,
                )
            )

    written = write_jsonl(args.output, rows)
    print(f"SFT trajectories written: {written} -> {args.output}")
    return 0


def build_sft_row(
    row_id: str,
    diagnostic: dict[str, Any],
    normalized: dict[str, Any],
    action: dict[str, Any],
) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": SFT_SYSTEM_PROMPT},
        {"role": "user", "content": _user_message(diagnostic, normalized)},
    ]
    skills = list(action.get("skills_to_call") or [])
    if skills:
        tool_call = {"name": "query_skill", "arguments": {"skill_name": skills[0]}}
        messages.append(
            {
                "role": "assistant",
                "content": "<think>Identify the failed constraints and call the most relevant retry skill.</think>\n"
                f"<tool_call>{json.dumps(tool_call, ensure_ascii=False, sort_keys=True)}</tool_call>",
            }
        )
        messages.append(
            {
                "role": "user",
                "content": "<tool_response>\n"
                f"Skill guidance for {skills[0]}: preserve passed constraints, repair failed constraints, and avoid regressions.\n"
                "</tool_response>",
            }
        )

    answer_payload = {
        "decision": action["decision"],
        "failure_types": action["failure_types"],
        "skills_to_call": action["skills_to_call"],
        "preserve_constraints": action["preserve_constraints"],
        "repair_constraints": action["repair_constraints"],
        "repair_strategy": action["repair_strategy"],
        "retry_prompt": action["retry_prompt"],
        "expected_improvement": action["expected_improvement"],
        "regression_risks": action["regression_risks"],
    }
    messages.append(
        {
            "role": "assistant",
            "content": "<think>Separate preserve constraints from repair targets and produce the retry action.</think>\n"
            f"<answer>{json.dumps(answer_payload, ensure_ascii=False, indent=2, sort_keys=True)}</answer>",
        }
    )
    return {
        "id": row_id,
        "trajectory_format": "compact",
        "messages": messages,
        "images": [],
        "diagnostic": diagnostic,
        "normalized_diagnostic": normalized,
        "teacher_retry_action": action,
    }


def build_full_episode_sft_row(
    row_id: str,
    diagnostic: dict[str, Any],
    normalized: dict[str, Any],
    action: dict[str, Any],
    *,
    retry_diagnostic: dict[str, Any] | None = None,
    diagnostic_detail: str = "compact",
) -> dict[str, Any]:
    source_prompt = str(diagnostic.get("prompt", "")).strip()
    first_image_id = f"{row_id}_candidate_0001"
    retry_image_id = f"{row_id}_candidate_0002"
    retry_judge = retry_diagnostic or _mock_improved_diagnostic(diagnostic)
    retry_passed = _diagnostic_passed(retry_judge)
    skills = list(action.get("skills_to_call") or [])
    primary_skill = skills[0] if skills else ""
    first_compact = _compact_diagnostic(diagnostic, normalized)
    retry_compact = _compact_retry_diagnostic(retry_judge)
    first_context = diagnostic if diagnostic_detail == "raw" else first_compact
    retry_context = retry_judge if diagnostic_detail == "raw" else retry_compact

    steps = [
        {
            "type": "parse_constraints",
            "role": "assistant",
            "content": "Parse the prompt into Geneval constraints before generating.",
            "constraints": _constraint_summary(diagnostic),
        },
        {
            "type": "generate_image",
            "role": "assistant",
            "attempt": "first",
            "tool_name": "generate_image",
            "content": "Call the mock image generator for the first attempt.",
            "arguments": {"prompt": source_prompt, "attempt": "first"},
            "observation": {"status": "mock_image_generated", "mock": True},
        },
        {
            "type": "judge_image",
            "role": "assistant",
            "attempt": "first",
            "tool_name": "judge_image",
            "content": "Call the mock Geneval judge on the first attempt.",
            "arguments": {"image_ref": "first_attempt", "expected": diagnostic.get("expected", {})},
            "observation": {"diagnostic": first_context},
        },
        {
            "type": "receive_geneval_diagnostic",
            "role": "assistant",
            "content": "Receive the Geneval diagnostic and separate passed constraints from failed constraints.",
            "normalized_diagnostic": normalized,
        },
        {
            "type": "query_skill",
            "role": "assistant",
            "tool_name": "query_skill",
            "skill_name": primary_skill,
            "content": "Call the relevant skill for the failed constraint type.",
            "arguments": {"skill_name": primary_skill, "failure_types": action["failure_types"]},
            "observation": {"guidance": _skill_guidance(primary_skill)},
        },
        {
            "type": "repair_prompt",
            "role": "assistant",
            "content": "Preserve passed constraints and produce the teacher retry action.",
            "teacher_retry_action": action,
            "repaired_prompt": action["retry_prompt"],
        },
        {
            "type": "generate_image",
            "role": "assistant",
            "attempt": "retry",
            "tool_name": "generate_image",
            "content": "Call the mock image generator for the retry attempt.",
            "arguments": {"prompt": action["retry_prompt"], "attempt": "retry"},
            "observation": {"status": "mock_image_generated", "mock": True},
        },
        {
            "type": "judge_image",
            "role": "assistant",
            "attempt": "retry",
            "tool_name": "judge_image",
            "content": "Call the mock Geneval judge on the retry attempt.",
            "arguments": {"image_ref": "retry_attempt", "expected": diagnostic.get("expected", {})},
            "observation": {"diagnostic": retry_context, "mock": retry_diagnostic is None},
        },
    ]

    submitted = action["decision"] == "retry" and retry_passed
    final_status = "passed_after_mock_retry" if submitted else "not_submitted"
    if action["decision"] == "submit":
        submitted = True
        final_status = "submitted_without_retry"
    elif action["decision"] == "discard":
        submitted = False
        final_status = "discarded_by_teacher"

    steps.append(
        {
            "type": "submit",
            "role": "assistant",
            "content": "Submit the retry candidate because the mock retry judge reports no regression."
            if submitted
            else "Do not submit because the retry was not judged successful.",
            "submitted": submitted,
            "final_status": final_status,
        }
    )

    messages = _full_episode_messages(
        source_prompt=source_prompt,
        diagnostic=first_context,
        normalized=normalized,
        action=action,
        retry_judge=retry_context,
        primary_skill=primary_skill,
        submitted=submitted,
        final_status=final_status,
    )
    assistant_trainable_messages = _assistant_trainable_messages(messages)
    tool_observations = _tool_observations(
        first_context=first_context,
        retry_context=retry_context,
        primary_skill=primary_skill,
    )

    return {
        "id": row_id,
        "trajectory_format": "full_episode",
        "masking_metadata": _masking_metadata(),
        "assistant_trainable_messages": assistant_trainable_messages,
        "tool_observations": tool_observations,
        "raw_detector_outputs": {
            "first_attempt_geneval": diagnostic,
            "retry_attempt_geneval": retry_judge if retry_diagnostic is not None else {},
        },
        "non_trainable_context": {
            "source_prompt": source_prompt,
            "expected_constraints": diagnostic.get("expected", {}),
            "generated_image_metadata": {
                "first_attempt_image_id": first_image_id,
                "retry_attempt_image_id": retry_image_id,
            },
            "diagnostic_detail": diagnostic_detail,
        },
        "messages": messages,
        "episode_steps": steps,
        "images": [],
        "diagnostic": first_context,
        "normalized_diagnostic": normalized,
        "teacher_retry_action": action,
        "mock_retry_diagnostic": retry_context,
        "outcome": {
            "submitted": submitted,
            "final_status": final_status,
            "notes": "Retry generation and retry judging are mocked; no image generator or real Geneval evaluator was called.",
        },
    }


def _user_message(diagnostic: dict[str, Any], normalized: dict[str, Any]) -> str:
    payload = {
        "task": "Convert this Geneval diagnostic into a retry action.",
        "diagnostic": diagnostic,
        "normalized_diagnostic": normalized,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _masking_metadata() -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "trainable_fields": ["assistant_trainable_messages"],
        "non_trainable_fields": [
            "tool_observations",
            "raw_detector_outputs",
            "non_trainable_context",
            "messages where role is user",
        ],
        "train_on": [
            "assistant diagnostic summaries",
            "assistant tool calls",
            "assistant retry decisions",
            "assistant repair prompts",
            "assistant submit/discard decisions",
        ],
        "do_not_train_on": [
            "raw Geneval detector outputs",
            "tool observations",
            "generated image metadata",
            "user prompts or context",
        ],
        "field_policy": {
            "assistant_trainable_messages": "train",
            "tool_observations": "mask",
            "raw_detector_outputs": "mask",
            "non_trainable_context": "mask",
            "messages": "derive masks by role; train assistant content only if it matches assistant_trainable_messages",
        },
    }


def _compact_diagnostic(diagnostic: dict[str, Any], normalized: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt": diagnostic.get("prompt", ""),
        "category": diagnostic.get("category", ""),
        "expected": deepcopy(diagnostic.get("expected", {})),
        "checks": deepcopy(diagnostic.get("checks", {})),
        "passed_constraints": deepcopy(normalized.get("passed_constraints", [])),
        "failed_constraints": deepcopy(normalized.get("failed_constraints", [])),
        "failure_types": deepcopy(normalized.get("failure_types", [])),
        "preserve_candidates": deepcopy(normalized.get("preserve_candidates", [])),
        "repair_targets": deepcopy(normalized.get("repair_targets", [])),
        "failure_reason": diagnostic.get("failure_reason", ""),
    }


def _compact_retry_diagnostic(retry_diagnostic: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt": retry_diagnostic.get("prompt", ""),
        "category": retry_diagnostic.get("category", ""),
        "expected": deepcopy(retry_diagnostic.get("expected", {})),
        "checks": deepcopy(retry_diagnostic.get("checks", {})),
        "failure_reason": retry_diagnostic.get("failure_reason", ""),
        "mock_improved": bool(retry_diagnostic.get("mock_improved", False)),
        "judge_reason": retry_diagnostic.get("judge_reason", ""),
    }


def _assistant_trainable_messages(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    trainable: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        content = message.get("content", "")
        trainable.append(
            {
                "role": "assistant",
                "content": content,
                "train": True,
                "target_type": _assistant_target_type(content),
            }
        )
    return trainable


def _assistant_target_type(content: str) -> str:
    if "<tool_call>" in content:
        return "tool_call"
    if "<parse_constraints>" in content or "<receive_geneval_diagnostic>" in content:
        return "diagnostic_summary"
    if "<repair_prompt>" in content:
        return "repair_prompt_and_retry_decision"
    if "<submit>" in content:
        return "submit_or_discard_decision"
    return "assistant_action"


def _tool_observations(
    *,
    first_context: dict[str, Any],
    retry_context: dict[str, Any],
    primary_skill: str,
) -> list[dict[str, Any]]:
    return [
        {
            "tool": "generate_image",
            "attempt": "first",
            "train": False,
            "observation": {"status": "mock_image_generated"},
        },
        {
            "tool": "judge_image",
            "attempt": "first",
            "train": False,
            "observation": {"diagnostic": first_context},
        },
        {
            "tool": "query_skill",
            "train": False,
            "observation": {"skill_name": primary_skill, "guidance": _skill_guidance(primary_skill)},
        },
        {
            "tool": "generate_image",
            "attempt": "retry",
            "train": False,
            "observation": {"status": "mock_image_generated"},
        },
        {
            "tool": "judge_image",
            "attempt": "retry",
            "train": False,
            "observation": {"diagnostic": retry_context},
        },
    ]


def _full_episode_messages(
    *,
    source_prompt: str,
    diagnostic: dict[str, Any],
    normalized: dict[str, Any],
    action: dict[str, Any],
    retry_judge: dict[str, Any],
    primary_skill: str,
    submitted: bool,
    final_status: str,
) -> list[dict[str, str]]:
    messages = [
        {"role": "system", "content": SFT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": "Run a full mocked Geneval retry episode.",
                    "prompt": source_prompt,
                    "expected_constraints": diagnostic.get("expected", {}),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
        },
        {
            "role": "assistant",
            "content": _tagged_json(
                "parse_constraints",
                {"constraints": _constraint_summary(diagnostic)},
            ),
        },
        {
            "role": "assistant",
            "content": _tool_call("generate_image", {"prompt": source_prompt, "attempt": "first"}),
        },
        {
            "role": "user",
            "content": _tool_response(
                {"tool": "generate_image", "status": "mock_image_generated", "mock": True}
            ),
        },
        {
            "role": "assistant",
            "content": _tool_call(
                "judge_image",
                {"image_ref": "first_attempt", "expected": diagnostic.get("expected", {})},
            ),
        },
        {
            "role": "user",
            "content": _tool_response({"tool": "judge_image", "diagnostic": diagnostic}),
        },
        {
            "role": "assistant",
            "content": _tagged_json(
                "receive_geneval_diagnostic",
                {"normalized_diagnostic": normalized},
            ),
        },
        {
            "role": "assistant",
            "content": _tool_call(
                "query_skill",
                {"skill_name": primary_skill, "failure_types": action["failure_types"]},
            ),
        },
        {
            "role": "user",
            "content": _tool_response(
                {
                    "tool": "query_skill",
                    "skill_name": primary_skill,
                    "guidance": _skill_guidance(primary_skill),
                }
            ),
        },
        {
            "role": "assistant",
            "content": _tagged_json(
                "repair_prompt",
                {
                    "preserve_constraints": action["preserve_constraints"],
                    "repair_constraints": action["repair_constraints"],
                    "retry_action": action,
                },
            ),
        },
        {
            "role": "assistant",
            "content": _tool_call(
                "generate_image",
                {"prompt": action["retry_prompt"], "attempt": "retry"},
            ),
        },
        {
            "role": "user",
            "content": _tool_response(
                {"tool": "generate_image", "status": "mock_image_generated", "mock": True}
            ),
        },
        {
            "role": "assistant",
            "content": _tool_call(
                "judge_image",
                {"image_ref": "retry_attempt", "expected": diagnostic.get("expected", {})},
            ),
        },
        {
            "role": "user",
            "content": _tool_response(
                {"tool": "judge_image", "diagnostic": retry_judge, "mock": True}
            ),
        },
        {
            "role": "assistant",
            "content": _tagged_json(
                "submit",
                {
                    "submitted": submitted,
                    "final_status": final_status,
                },
            ),
        },
    ]
    return messages


def _extract_retry_diagnostic(action_row: dict[str, Any]) -> dict[str, Any] | None:
    for key in (
        "retry_diagnostic",
        "second_diagnostic",
        "improved_diagnostic",
        "retry_geneval_diagnostic",
    ):
        value = action_row.get(key)
        if isinstance(value, dict):
            return value
    return None


def _mock_improved_diagnostic(diagnostic: dict[str, Any]) -> dict[str, Any]:
    improved = {
        "prompt": diagnostic.get("prompt", ""),
        "category": diagnostic.get("category", ""),
        "expected": deepcopy(diagnostic.get("expected", {})),
    }
    checks = improved.get("checks")
    source_checks = diagnostic.get("checks")
    if isinstance(source_checks, dict) and source_checks:
        checks = source_checks
    if isinstance(checks, dict) and checks:
        improved["checks"] = {str(key): True for key in checks}
    else:
        improved["checks"] = {"mock_retry_judge": True}
    improved["failure_reason"] = ""
    improved["mock_improved"] = True
    improved["judge_reason"] = "Mock retry judge marks all tracked Geneval checks as passed."
    return improved


def _diagnostic_passed(diagnostic: dict[str, Any]) -> bool:
    checks = diagnostic.get("checks")
    if not isinstance(checks, dict) or not checks:
        return False
    return all(value is True for value in checks.values())


def _constraint_summary(diagnostic: dict[str, Any]) -> dict[str, Any]:
    expected = diagnostic.get("expected") if isinstance(diagnostic.get("expected"), dict) else {}
    return {
        "objects": expected.get("objects", []),
        "counts": expected.get("count", {}),
        "colors": expected.get("color", {}),
        "spatial": expected.get("spatial", []),
    }


def _skill_guidance(skill_name: str) -> str:
    skill = DEFAULT_SKILLS.get(skill_name)
    if skill is None:
        return "Preserve passed constraints, repair failed constraints, and avoid regressions."
    return f"{skill.summary} Preserve passed constraints before applying the repair."


def _tool_call(name: str, arguments: dict[str, Any]) -> str:
    return "<tool_call>" + json.dumps(
        {"name": name, "arguments": arguments},
        ensure_ascii=False,
        sort_keys=True,
    ) + "</tool_call>"


def _tool_response(payload: dict[str, Any]) -> str:
    return "<tool_response>" + json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
    ) + "</tool_response>"


def _tagged_json(tag: str, payload: dict[str, Any]) -> str:
    return f"<{tag}>" + json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + f"</{tag}>"


if __name__ == "__main__":
    raise SystemExit(main())
