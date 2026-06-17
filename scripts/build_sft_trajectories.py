#!/usr/bin/env python3
"""Build SFT trajectories from diagnostics and teacher retry actions."""

from __future__ import annotations

import argparse
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


SFT_SYSTEM_PROMPT = """You are a Gen-Retry student. Use Geneval diagnostics to preserve passed constraints, repair failed constraints, call the right skill, retry generation, and submit only after improvement."""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Gen-Retry SFT trajectory JSONL.")
    parser.add_argument("--diagnostics", default="data/raw/geneval_diagnostics.jsonl")
    parser.add_argument("--teacher-actions", default="data/processed/teacher_retry_actions.jsonl")
    parser.add_argument("--output", default="data/processed/geneval_retry_sft.jsonl")
    args = parser.parse_args()

    diagnostics = read_json_or_jsonl(args.diagnostics)
    actions = read_json_or_jsonl(args.teacher_actions)
    diagnostics_by_id = {
        record_id(record, index): extract_diagnostic(record)
        for index, record in enumerate(diagnostics)
    }

    rows = []
    for index, action_row in enumerate(actions):
        row_id = str(action_row.get("id") or f"sample_{index:06d}")
        diagnostic = action_row.get("diagnostic")
        if not isinstance(diagnostic, dict):
            diagnostic = diagnostics_by_id.get(row_id)
        if not isinstance(diagnostic, dict):
            raise ValueError(f"No diagnostic found for teacher action row {row_id}")
        normalized = action_row.get("normalized_diagnostic")
        if not isinstance(normalized, dict):
            normalized = normalize_geneval_diagnostic(diagnostic)
        action = validate_teacher_retry_action(action_row.get("teacher_retry_action")).to_dict()
        rows.append(build_sft_row(row_id, diagnostic, normalized, action))

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
        "messages": messages,
        "images": [],
        "diagnostic": diagnostic,
        "normalized_diagnostic": normalized,
        "teacher_retry_action": action,
    }


def _user_message(diagnostic: dict[str, Any], normalized: dict[str, Any]) -> str:
    payload = {
        "task": "Convert this Geneval diagnostic into a retry action.",
        "diagnostic": diagnostic,
        "normalized_diagnostic": normalized,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())
