#!/usr/bin/env python3
"""Prepare a prompt JSONL subset from GenEval2 metadata."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.utils.io import read_jsonl, write_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract a GenEval2 prompt subset for Gen-Retry collection.")
    parser.add_argument("--input", default="../GenEval2/geneval2_data.jsonl")
    parser.add_argument("--output", required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skill", action="append", default=[], help="Keep rows containing this skill. Repeatable.")
    parser.add_argument("--min-atom-count", type=int)
    parser.add_argument("--max-atom-count", type=int)
    parser.add_argument("--prompt-contains")
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    filtered = [
        _normalize_row(row, index)
        for index, row in enumerate(rows)
        if _keep_row(
            row,
            skills=set(args.skill),
            min_atom_count=args.min_atom_count,
            max_atom_count=args.max_atom_count,
            prompt_contains=args.prompt_contains,
        )
    ]
    if args.offset:
        filtered = filtered[args.offset :]
    if args.limit:
        filtered = filtered[: args.limit]

    written = write_jsonl(args.output, filtered)
    print(f"wrote {written} GenEval2 prompt row(s) -> {args.output}")
    return 0


def _keep_row(
    row: dict[str, Any],
    *,
    skills: set[str],
    min_atom_count: int | None,
    max_atom_count: int | None,
    prompt_contains: str | None,
) -> bool:
    prompt = str(row.get("prompt", ""))
    if not prompt.strip():
        return False
    atom_count = int(row.get("atom_count", 0) or 0)
    if min_atom_count is not None and atom_count < min_atom_count:
        return False
    if max_atom_count is not None and atom_count > max_atom_count:
        return False
    row_skills = {str(item) for item in row.get("skills", []) if str(item).strip()}
    if skills and not skills.intersection(row_skills):
        return False
    if prompt_contains and prompt_contains.lower() not in prompt.lower():
        return False
    return True


def _normalize_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "prompt": str(row.get("prompt", "")).strip(),
        "source": "geneval2",
        "source_index": index,
        "atom_count": row.get("atom_count"),
        "vqa_list": row.get("vqa_list", []),
        "skills": row.get("skills", []),
    }


if __name__ == "__main__":
    raise SystemExit(main())
