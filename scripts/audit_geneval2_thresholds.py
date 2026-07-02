#!/usr/bin/env python3
"""Audit GenEval2 training-time diagnostic thresholds.

The atom threshold reported here is only for constructing retry-training
diagnostics. It is not a replacement for official GenEval2 benchmark scoring.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.evaluators.geneval2_result_normalizer import (  # noqa: E402
    load_geneval2_score_rows,
    normalize_geneval2_score_list,
)
from gen_retry.schemas.episode import Episode  # noqa: E402
from gen_retry.utils.io import read_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit GenEval2 atom thresholds for retry-data construction.")
    parser.add_argument("--input", required=True, help="score_lists/atom rows JSON, JSONL, normalized reports, or episode dir.")
    parser.add_argument("--thresholds", default="0.5,0.9,0.95")
    parser.add_argument("--output", required=True)
    parser.add_argument("--benchmark-data", help="Optional GenEval2 geneval2_data.jsonl for official score_lists.")
    parser.add_argument("--aggregate-by", default="prompt_id")
    args = parser.parse_args()

    thresholds = [_threshold(item) for item in args.thresholds.split(",") if item.strip()]
    rows = _load_rows(args.input, benchmark_data=args.benchmark_data)
    report = {
        "input": args.input,
        "threshold_note": (
            "These thresholds are for training-time diagnostic normalization only; "
            "official GenEval2 benchmark scoring remains unchanged."
        ),
        "thresholds": [],
    }
    for threshold in thresholds:
        reports = normalize_geneval2_score_list(
            rows,
            aggregate_by=args.aggregate_by,
            atom_threshold=threshold,
        )
        report["thresholds"].append(_summarize_threshold(threshold, reports))
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote Geneval2 threshold audit -> {target}")
    return 0


def _load_rows(path: str, *, benchmark_data: str | None) -> list[dict[str, Any]]:
    source = Path(path)
    if source.is_dir():
        return _rows_from_episode_dir(source)
    try:
        return load_geneval2_score_rows(source, benchmark_data=benchmark_data)
    except Exception:
        return _rows_from_normalized_reports(source)


def _rows_from_episode_dir(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    normalized_rows: list[dict[str, Any]] = []
    for episode_path in sorted(path.glob("*.json")):
        episode = Episode.from_dict(read_json(episode_path))
        for attempt in episode.attempts:
            raw_report = attempt.eval_report.raw_report
            raw_rows = raw_report.get("rows") if isinstance(raw_report, dict) else None
            if isinstance(raw_rows, list):
                group_id = f"{episode.episode_id}:attempt_{attempt.round}"
                for row in raw_rows:
                    if isinstance(row, dict):
                        item = dict(row)
                        item.setdefault("original_prompt_id", item.get("prompt_id"))
                        item.setdefault("image_id", group_id)
                        item["prompt_id"] = group_id
                        rows.append(item)
            normalized_rows.extend(
                _rows_from_report(
                    attempt.eval_report.to_dict(),
                    group=f"{episode.episode_id}:attempt_{attempt.round}",
                )
            )
    if not rows:
        rows = normalized_rows
    if not rows:
        raise ValueError(f"no GenEval2 raw rows or normalized reports found under {path}")
    return rows


def _rows_from_normalized_reports(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    records = [json.loads(line) for line in text.splitlines()] if path.suffix == ".jsonl" else json.loads(text)
    if isinstance(records, dict):
        records = records.get("reports", records.get("data", [records]))
    if not isinstance(records, list):
        raise ValueError(f"{path} does not contain rows or reports")
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        report = record.get("normalized_report", record)
        if not isinstance(report, dict):
            continue
        group = str(record.get("group_id", index))
        rows.extend(_rows_from_report(report, group=group))
    if not rows:
        raise ValueError(f"no normalized report constraints found in {path}")
    return rows


def _rows_from_report(report: dict[str, Any], *, group: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("passed_constraints", "failed_constraints", "uncertain_constraints"):
        status = key.split("_", 1)[0]
        for constraint in report.get(key, []) or []:
            if not isinstance(constraint, dict):
                continue
            details = constraint.get("details") if isinstance(constraint.get("details"), dict) else {}
            rows.append(
                {
                    "prompt_id": group,
                    "question": constraint.get("target", ""),
                    "answer": constraint.get("expected", ""),
                    "score": details.get("score"),
                    "skill": details.get("skill", constraint.get("type", "")),
                    "status": status,
                }
            )
    return rows


def _summarize_threshold(threshold: float, reports: dict[str, Any]) -> dict[str, Any]:
    failed_counts = [len(report.failed_constraints) for report in reports.values()]
    passed_counts = [len(report.passed_constraints) for report in reports.values()]
    scores = [report.score for report in reports.values()]
    failure_types: Counter[str] = Counter()
    critical_count = 0
    no_failed = 0
    for report in reports.values():
        if not report.failed_constraints:
            no_failed += 1
        if report.critical_failure_types:
            critical_count += 1
        for constraint in report.failed_constraints:
            failure_types[constraint.type] += 1
    total = len(reports)
    retry_trigger_count = total - no_failed
    return {
        "atom_threshold": threshold,
        "groups": total,
        "average_normalized_score": mean(scores) if scores else 0.0,
        "average_failed_atom_count": mean(failed_counts) if failed_counts else 0.0,
        "average_passed_atom_count": mean(passed_counts) if passed_counts else 0.0,
        "retry_trigger_rate": retry_trigger_count / total if total else 0.0,
        "retry_trigger_count": retry_trigger_count,
        "failure_type_distribution": dict(sorted(failure_types.items())),
        "samples_with_no_failed_constraints": no_failed,
        "samples_with_critical_failures": critical_count,
    }


def _threshold(text: str) -> float:
    value = float(text)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"threshold must be between 0 and 1: {text}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
