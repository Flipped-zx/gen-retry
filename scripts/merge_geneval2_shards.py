#!/usr/bin/env python3
"""Merge GenEval2 shard outputs into one candidate-level diagnostics directory."""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.utils.io import read_json, read_jsonl, write_json, write_jsonl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge sharded GenEval2 outputs.")
    parser.add_argument("--shard-dir", action="append", default=[], help="Shard output directory. Can be repeated.")
    parser.add_argument("--shard-glob", help="Glob for shard output directories.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-count", type=int)
    args = parser.parse_args()

    shard_dirs = [Path(value) for value in args.shard_dir]
    if args.shard_glob:
        shard_dirs.extend(Path(value) for value in glob.glob(args.shard_glob))
    shard_dirs = sorted({path.resolve() for path in shard_dirs})
    if not shard_dirs:
        raise ValueError("provide at least one --shard-dir or --shard-glob")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = merge_shards(shard_dirs, output_dir=output_dir, expected_count=args.expected_count)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary["status"] == "ok" else 1


def merge_shards(
    shard_dirs: list[Path],
    *,
    output_dir: Path,
    expected_count: int | None = None,
) -> dict[str, Any]:
    diagnostic_jobs: list[dict[str, Any]] = []
    atom_rows: list[dict[str, Any]] = []
    normalized_reports: list[dict[str, Any]] = []
    score_lists_by_candidate: dict[str, Any] = {}
    image_paths: dict[str, str] = {}
    plans: list[dict[str, Any]] = []
    issues: list[str] = []

    for shard_dir in shard_dirs:
        if not shard_dir.exists():
            issues.append(f"missing shard dir: {shard_dir}")
            continue
        diagnostic_jobs.extend(_read_jsonl_if_exists(shard_dir / "diagnostic_jobs.jsonl"))
        atom_rows.extend(_read_jsonl_if_exists(shard_dir / "atom_rows.jsonl"))
        normalized_reports.extend(_read_jsonl_if_exists(shard_dir / "normalized_reports.jsonl"))
        if (shard_dir / "eval_image_paths.json").exists():
            image_paths.update(read_json(shard_dir / "eval_image_paths.json"))
        if (shard_dir / "geneval2_batch_plan.json").exists():
            plans.append(read_json(shard_dir / "geneval2_batch_plan.json"))
        raw_scores_path = shard_dir / "raw_score_lists.json"
        if raw_scores_path.exists():
            raw_scores = json.loads(raw_scores_path.read_text(encoding="utf-8"))
            shard_jobs = _read_jsonl_if_exists(shard_dir / "diagnostic_jobs.jsonl")
            if isinstance(raw_scores, list) and len(raw_scores) == len(shard_jobs):
                for job, scores in zip(shard_jobs, raw_scores, strict=True):
                    score_lists_by_candidate[str(job.get("candidate_id", ""))] = scores
            else:
                issues.append(f"raw score count mismatch in {raw_scores_path}")

    report_ids = [str(row.get("candidate_id", "")) for row in normalized_reports]
    duplicate_reports = sorted(_duplicates(report_ids))
    if duplicate_reports:
        issues.append(f"duplicate normalized report candidate_id(s): {duplicate_reports[:10]}")
    job_ids = [str(row.get("candidate_id", "")) for row in diagnostic_jobs]
    duplicate_jobs = sorted(_duplicates(job_ids))
    if duplicate_jobs:
        issues.append(f"duplicate diagnostic job candidate_id(s): {duplicate_jobs[:10]}")
    if expected_count is not None and len(set(report_ids)) != expected_count:
        issues.append(f"normalized report count {len(set(report_ids))} != expected {expected_count}")

    diagnostic_jobs = sorted(diagnostic_jobs, key=lambda row: str(row.get("candidate_id", "")))
    atom_rows = sorted(
        atom_rows,
        key=lambda row: (str(row.get("candidate_id", "")), int(row.get("atom_index", 0))),
    )
    normalized_reports = sorted(normalized_reports, key=lambda row: str(row.get("candidate_id", "")))
    write_jsonl(output_dir / "diagnostic_jobs.jsonl", diagnostic_jobs)
    write_jsonl(output_dir / "atom_rows.jsonl", atom_rows)
    write_jsonl(output_dir / "normalized_reports.jsonl", normalized_reports)
    write_json(output_dir / "eval_image_paths.json", dict(sorted(image_paths.items())))
    write_json(
        output_dir / "raw_score_lists.by_candidate.json",
        dict(sorted(score_lists_by_candidate.items())),
    )
    write_json(
        output_dir / "geneval2_batch_plan.json",
        {
            "shard_dirs": [str(path) for path in shard_dirs],
            "shard_plans": plans,
            "planned_jobs": len(diagnostic_jobs),
            "normalized_reports": len(normalized_reports),
            "expected_count": expected_count,
            "issues": issues,
        },
    )
    summary = {
        "status": "error" if issues else "ok",
        "shard_count": len(shard_dirs),
        "diagnostic_jobs": len(diagnostic_jobs),
        "atom_rows": len(atom_rows),
        "normalized_reports": len(normalized_reports),
        "score_lists_by_candidate": len(score_lists_by_candidate),
        "output_dir": str(output_dir),
        "issues": issues,
    }
    write_json(output_dir / "merge_summary.json", summary)
    return summary


def _read_jsonl_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return read_jsonl(path)


def _duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


if __name__ == "__main__":
    raise SystemExit(main())
