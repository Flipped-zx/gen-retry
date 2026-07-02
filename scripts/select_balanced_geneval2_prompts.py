#!/usr/bin/env python3
"""Select a balanced 100-prompt GenEval2 pilot set.

The selector is metadata-only: it does not call generation, teacher APIs, or
GenEval2 evaluation. It prioritizes coverage across retry-relevant constraint
families while keeping deterministic output for resumable pilots.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.utils.io import write_json, write_jsonl  # noqa: E402


BUCKET_ORDER = [
    "count",
    "object",
    "attribute",
    "color_binding",
    "position_spatial",
    "relation_action",
    "multi_constraint",
    "high_atom_count",
]

COLOR_WORDS = {
    "black",
    "blue",
    "brown",
    "cyan",
    "gray",
    "green",
    "grey",
    "orange",
    "pink",
    "purple",
    "red",
    "white",
    "yellow",
}
POSITION_WORDS = {
    "above",
    "behind",
    "below",
    "front",
    "left",
    "right",
    "under",
    "over",
    "top",
}
RELATION_WORDS = {
    "chasing",
    "holding",
    "jumping",
    "playing",
    "riding",
    "standing",
    "sitting",
    "wearing",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Select balanced GenEval2 prompts for a retry pilot.")
    parser.add_argument("--input", default="../GenEval2/geneval2_data.jsonl")
    parser.add_argument("--output", default="data/prompts/geneval2_balanced_100.jsonl")
    parser.add_argument("--num-prompts", type=int, default=100)
    parser.add_argument("--high-atom-threshold", type=int, default=7)
    parser.add_argument("--summary-json")
    parser.add_argument("--summary-md")
    args = parser.parse_args()

    if args.num_prompts <= 0:
        raise ValueError("--num-prompts must be positive")

    rows = [
        _normalize_row(row, row_index=index, high_atom_threshold=args.high_atom_threshold)
        for index, row in enumerate(_read_jsonl(args.input))
    ]
    rows = [row for row in rows if row["prompt"]]
    if len(rows) < args.num_prompts:
        raise ValueError(f"input only has {len(rows)} non-empty prompts; need {args.num_prompts}")

    selected = select_balanced(rows, args.num_prompts)
    written = write_jsonl(args.output, [_public_row(row) for row in selected])

    summary = build_summary(
        selected=selected,
        input_rows=len(rows),
        requested=args.num_prompts,
        high_atom_threshold=args.high_atom_threshold,
    )
    summary_json = Path(args.summary_json) if args.summary_json else Path(args.output).with_suffix(".summary.json")
    summary_md = Path(args.summary_md) if args.summary_md else Path(args.output).with_suffix(".summary.md")
    write_json(summary_json, summary)
    summary_md.parent.mkdir(parents=True, exist_ok=True)
    summary_md.write_text(_summary_markdown(summary), encoding="utf-8")

    print(f"wrote {written} balanced GenEval2 prompt row(s) -> {args.output}")
    print(f"wrote summary JSON -> {summary_json}")
    print(f"wrote summary markdown -> {summary_md}")
    return 0


def select_balanced(rows: list[dict[str, Any]], num_prompts: int) -> list[dict[str, Any]]:
    by_bucket: dict[str, list[dict[str, Any]]] = {}
    for bucket in BUCKET_ORDER:
        bucket_rows = [row for row in rows if bucket in row["sampling_tags"]]
        bucket_rows.sort(key=_selection_key)
        by_bucket[bucket] = bucket_rows

    selected: list[dict[str, Any]] = []
    used_prompt_ids: set[str] = set()
    base_quota, remainder = divmod(num_prompts, len(BUCKET_ORDER))
    quotas = {
        bucket: base_quota + (1 if index < remainder else 0)
        for index, bucket in enumerate(BUCKET_ORDER)
    }

    for bucket in BUCKET_ORDER:
        needed = quotas[bucket]
        for row in by_bucket[bucket]:
            if len(selected) >= num_prompts or needed <= 0:
                break
            if row["prompt_id"] in used_prompt_ids:
                continue
            selected.append({**row, "sampling_bucket": bucket})
            used_prompt_ids.add(row["prompt_id"])
            needed -= 1

    if len(selected) < num_prompts:
        remaining = [row for row in rows if row["prompt_id"] not in used_prompt_ids]
        remaining.sort(key=_selection_key)
        for row in remaining:
            if len(selected) >= num_prompts:
                break
            bucket = row["sampling_tags"][0] if row["sampling_tags"] else "general"
            selected.append({**row, "sampling_bucket": bucket})
            used_prompt_ids.add(row["prompt_id"])

    selected.sort(key=lambda row: (BUCKET_ORDER.index(row["sampling_bucket"]) if row["sampling_bucket"] in BUCKET_ORDER else 99, row["source_index"]))
    return selected[:num_prompts]


def build_summary(
    *,
    selected: list[dict[str, Any]],
    input_rows: int,
    requested: int,
    high_atom_threshold: int,
) -> dict[str, Any]:
    atom_counts = [int(row["atom_count"]) for row in selected]
    skill_counter: Counter[str] = Counter()
    tag_counter: Counter[str] = Counter()
    for row in selected:
        skill_counter.update(row["skills"])
        tag_counter.update(row["sampling_tags"])
    return {
        "requested": requested,
        "selected": len(selected),
        "input_rows": input_rows,
        "high_atom_threshold": high_atom_threshold,
        "sampling_bucket_counts": dict(Counter(row["sampling_bucket"] for row in selected)),
        "sampling_tag_counts": dict(tag_counter),
        "skill_counts": dict(skill_counter),
        "atom_count": {
            "min": min(atom_counts) if atom_counts else 0,
            "max": max(atom_counts) if atom_counts else 0,
            "average": round(sum(atom_counts) / len(atom_counts), 3) if atom_counts else 0.0,
            "ge_high_atom_threshold": sum(1 for value in atom_counts if value >= high_atom_threshold),
        },
        "source_index": {
            "min": min(int(row["source_index"]) for row in selected) if selected else 0,
            "max": max(int(row["source_index"]) for row in selected) if selected else 0,
        },
        "prompt_ids": [row["prompt_id"] for row in selected],
    }


def _normalize_row(row: dict[str, Any], *, row_index: int, high_atom_threshold: int) -> dict[str, Any]:
    prompt = str(row.get("prompt", "")).strip()
    source_index = int(row.get("source_index", row_index))
    skills = [str(item).strip() for item in row.get("skills", []) if str(item).strip()]
    vqa_list = row.get("vqa_list", [])
    atom_count = int(row.get("atom_count", len(vqa_list) if isinstance(vqa_list, list) else 0) or 0)
    tags = _sampling_tags(prompt=prompt, skills=skills, atom_count=atom_count, high_atom_threshold=high_atom_threshold)
    return {
        "prompt_id": _prompt_id(source_index, prompt),
        "source": str(row.get("source", "geneval2")),
        "source_index": source_index,
        "prompt": prompt,
        "skills": skills,
        "atom_count": atom_count,
        "vqa_list": vqa_list if isinstance(vqa_list, list) else [],
        "sampling_tags": tags,
        "sampling_bucket": "",
        "skill_counts": dict(Counter(skills)),
        "static_priority": _static_priority(prompt=prompt, skills=skills, atom_count=atom_count, tags=tags),
    }


def _sampling_tags(
    *,
    prompt: str,
    skills: list[str],
    atom_count: int,
    high_atom_threshold: int,
) -> list[str]:
    lower_prompt = prompt.lower()
    words = set(lower_prompt.replace(",", " ").replace(".", " ").split())
    skill_set = set(skills)
    tags: list[str] = []
    if "count" in skill_set:
        tags.append("count")
    if "object" in skill_set:
        tags.append("object")
    if "attribute" in skill_set:
        tags.append("attribute")
    if "attribute" in skill_set and (words & COLOR_WORDS):
        tags.append("color_binding")
    if "position" in skill_set or words & POSITION_WORDS:
        tags.append("position_spatial")
    if "verb" in skill_set or words & RELATION_WORDS:
        tags.append("relation_action")
    if atom_count >= 5 or len(skill_set) >= 3:
        tags.append("multi_constraint")
    if atom_count >= high_atom_threshold:
        tags.append("high_atom_count")
    return [bucket for bucket in BUCKET_ORDER if bucket in tags]


def _static_priority(*, prompt: str, skills: list[str], atom_count: int, tags: list[str]) -> float:
    counts = Counter(skills)
    score = float(atom_count)
    score += len(set(skills)) * 1.5
    score += counts.get("count", 0) * 0.7
    score += counts.get("attribute", 0) * 0.5
    score += counts.get("position", 0) * 1.3
    score += counts.get("verb", 0) * 1.5
    if "color_binding" in tags:
        score += 1.0
    if "multi_constraint" in tags:
        score += 1.0
    if "high_atom_count" in tags:
        score += 2.0
    if "," in prompt or " and " in prompt.lower():
        score += 0.5
    return round(score, 3)


def _selection_key(row: dict[str, Any]) -> tuple[float, int, int]:
    return (-float(row["static_priority"]), -int(row["atom_count"]), int(row["source_index"]))


def _prompt_id(source_index: int, prompt: str) -> str:
    digest = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8]
    return f"geneval2_{source_index:05d}_{digest}"


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt_id": row["prompt_id"],
        "source": row["source"],
        "source_index": row["source_index"],
        "prompt": row["prompt"],
        "skills": row["skills"],
        "atom_count": row["atom_count"],
        "vqa_list": row["vqa_list"],
        "sampling_bucket": row["sampling_bucket"],
        "sampling_tags": row["sampling_tags"],
        "skill_counts": row["skill_counts"],
        "static_priority": row["static_priority"],
    }


def _summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# GenEval2 Balanced Prompt Selection",
        "",
        f"- requested: {summary['requested']}",
        f"- selected: {summary['selected']}",
        f"- input_rows: {summary['input_rows']}",
        f"- high_atom_threshold: {summary['high_atom_threshold']}",
        "",
        "## Sampling Buckets",
        "",
    ]
    for bucket, count in sorted(summary["sampling_bucket_counts"].items()):
        lines.append(f"- {bucket}: {count}")
    lines.extend(["", "## Skills", ""])
    for skill, count in sorted(summary["skill_counts"].items()):
        lines.append(f"- {skill}: {count}")
    atom = summary["atom_count"]
    lines.extend(
        [
            "",
            "## Atom Count",
            "",
            f"- min: {atom['min']}",
            f"- max: {atom['max']}",
            f"- average: {atom['average']}",
            f"- >= threshold: {atom['ge_high_atom_threshold']}",
            "",
        ]
    )
    return "\n".join(lines)


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError(f"{path}:{lineno} is not a JSON object")
        rows.append(item)
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
