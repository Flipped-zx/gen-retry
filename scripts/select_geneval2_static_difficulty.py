#!/usr/bin/env python3
"""Select GenEval2 prompts by static retry-difficulty heuristics.

This does not call image generation or evaluators. It ranks prompts from the
metadata only, so it is useful before spending API budget.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.utils.io import write_jsonl


NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

HARD_ATTRIBUTES = {
    "transparent",
    "wooden",
    "metal",
    "plastic",
    "stone",
    "glass",
    "ceramic",
    "rubber",
}

RELATION_MARKERS = {
    "left",
    "right",
    "front",
    "behind",
    "above",
    "below",
    "under",
    "over",
    "holding",
    "riding",
    "wearing",
    "playing",
    "chasing",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank GenEval2 prompts by static difficulty.")
    parser.add_argument("--input", default="../GenEval2/geneval2_data.jsonl")
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--min-atom-count", type=int)
    parser.add_argument("--max-atom-count", type=int)
    parser.add_argument("--require-skill", action="append", default=[])
    parser.add_argument("--exclude-skill", action="append", default=[])
    parser.add_argument("--bucket", choices=["all", "medium", "hard", "very_hard"], default="all")
    args = parser.parse_args()

    rows = []
    for index, row in enumerate(_read_jsonl(args.input)):
        score, reasons = static_difficulty_score(row)
        if score < args.min_score:
            continue
        atom_count = int(row.get("atom_count", 0) or 0)
        if args.min_atom_count is not None and atom_count < args.min_atom_count:
            continue
        if args.max_atom_count is not None and atom_count > args.max_atom_count:
            continue
        skills = {str(item) for item in row.get("skills", [])}
        if args.require_skill and not set(args.require_skill).issubset(skills):
            continue
        if args.exclude_skill and set(args.exclude_skill) & skills:
            continue
        bucket = _bucket(score)
        if args.bucket != "all" and bucket != args.bucket:
            continue
        rows.append(
            {
                "prompt": str(row.get("prompt", "")).strip(),
                "source": "geneval2",
                "source_index": index,
                "atom_count": row.get("atom_count"),
                "skills": row.get("skills", []),
                "vqa_list": row.get("vqa_list", []),
                "static_difficulty_score": score,
                "difficulty_bucket": bucket,
                "difficulty_reasons": reasons,
                "skill_counts": dict(Counter(str(item) for item in row.get("skills", []))),
            }
        )

    rows.sort(
        key=lambda item: (
            -float(item["static_difficulty_score"]),
            -int(item.get("atom_count") or 0),
            int(item["source_index"]),
        )
    )
    if args.limit:
        rows = rows[: args.limit]
    written = write_jsonl(args.output, rows)
    print(f"wrote {written} ranked GenEval2 prompt row(s) -> {args.output}")
    return 0


def static_difficulty_score(row: dict[str, Any]) -> tuple[float, list[str]]:
    prompt = str(row.get("prompt", "")).lower()
    skills = [str(item) for item in row.get("skills", [])]
    counts = Counter(skills)
    atom_count = int(row.get("atom_count", 0) or 0)
    score = 0.0
    reasons: list[str] = []

    if atom_count:
        score += max(0, atom_count - 3) * 1.2
        if atom_count >= 7:
            reasons.append(f"high_atomicity={atom_count}")

    count_atoms = counts.get("count", 0)
    object_atoms = counts.get("object", 0)
    attribute_atoms = counts.get("attribute", 0)
    position_atoms = counts.get("position", 0)
    verb_atoms = counts.get("verb", 0)

    if count_atoms >= 2:
        score += 1.5 + 0.4 * count_atoms
        reasons.append(f"multiple_count_atoms={count_atoms}")
    elif count_atoms == 1:
        score += 0.5

    if object_atoms >= 3:
        score += 1.0 + 0.2 * object_atoms
        reasons.append(f"many_object_atoms={object_atoms}")

    if attribute_atoms >= 2:
        score += 1.0 + 0.25 * attribute_atoms
        reasons.append(f"attribute_binding_atoms={attribute_atoms}")
    elif attribute_atoms == 1:
        score += 0.3

    if position_atoms:
        score += 2.0 + 0.6 * position_atoms
        reasons.append(f"spatial_position_atoms={position_atoms}")

    if verb_atoms:
        score += 2.4 + 0.7 * verb_atoms
        reasons.append(f"verb_relation_atoms={verb_atoms}")

    max_number = _max_number(prompt)
    if max_number >= 5:
        score += 1.5 + 0.25 * (max_number - 5)
        reasons.append(f"large_count={max_number}")
    elif max_number >= 3:
        score += 0.5

    hard_attrs = sorted(word for word in HARD_ATTRIBUTES if word in prompt)
    if hard_attrs:
        score += 0.8
        reasons.append("hard_attribute=" + ",".join(hard_attrs))

    relation_words = sorted(word for word in RELATION_MARKERS if word in prompt)
    if relation_words:
        score += 0.5
        reasons.append("relation_words=" + ",".join(relation_words[:4]))

    if " and " in prompt or "," in prompt:
        score += 0.5
        reasons.append("multi_clause_prompt")

    if not reasons:
        reasons.append("low_static_complexity")
    return round(score, 3), reasons


def _bucket(score: float) -> str:
    if score >= 11:
        return "very_hard"
    if score >= 7:
        return "hard"
    if score >= 4:
        return "medium"
    return "easy"


def _max_number(prompt: str) -> int:
    values = [value for word, value in NUMBER_WORDS.items() if word in prompt.split()]
    return max(values) if values else 0


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            rows.append(item)
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
