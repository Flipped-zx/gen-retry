#!/usr/bin/env python3
"""Normalize official GenEval2 score outputs into Gen-Retry reports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.evaluators.geneval2_result_normalizer import (
    load_geneval2_score_rows,
    normalize_geneval2_score_list,
)
from gen_retry.utils.io import write_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize GenEval2 score_lists.json into JSONL reports.")
    parser.add_argument("--input", required=True, help="Official GenEval2 score_lists.json, JSONL, or atom-row JSON.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--benchmark-data", help="Optional GenEval2 geneval2_data.jsonl to join VQA questions/skills.")
    parser.add_argument("--aggregate-by", default="prompt_id")
    parser.add_argument(
        "--atom-threshold",
        type=float,
        default=0.5,
        help=(
            "Training-time atom threshold for diagnostic normalization only; "
            "official GenEval2 benchmark scoring remains unchanged."
        ),
    )
    args = parser.parse_args()

    rows = load_geneval2_score_rows(args.input, benchmark_data=args.benchmark_data)
    reports = normalize_geneval2_score_list(
        rows,
        aggregate_by=args.aggregate_by,
        atom_threshold=args.atom_threshold,
    )
    output_rows = []
    for group_id, report in sorted(reports.items()):
        raw_rows = report.raw_report.get("rows", []) if isinstance(report.raw_report, dict) else []
        first = raw_rows[0] if raw_rows and isinstance(raw_rows[0], dict) else {}
        output_rows.append(
            {
                "group_id": group_id,
                "prompt": first.get("prompt", ""),
                "image_id": first.get("image_id", first.get("image_path", "")),
                "image_path": first.get("image_path", ""),
                "raw_rows_count": len(raw_rows),
                "normalized_report": report.to_dict(),
            }
        )
    written = write_jsonl(args.output, output_rows)
    print(f"normalized {written} GenEval2 report(s) -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
