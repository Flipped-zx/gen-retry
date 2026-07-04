#!/usr/bin/env python3
"""Prepare returned GenEval2 diagnostics for retry teacher planning."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.geneval2_retry_prepare import (  # noqa: E402
    Geneval2RetryPrepareConfig,
    prepare_geneval2_retry_inputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize returned GenEval2 diagnostics, rebuild first-pass packages with "
            "initial-plan context, and preflight them before teacher API calls."
        )
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--initial-plan-dir", required=True)
    parser.add_argument("--diagnostic-jobs", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--eval-results", help="Already-normalized GenEval2 reports JSONL.")
    group.add_argument("--raw-score-lists", help="Official GenEval2 raw_score_lists.json or compatible score rows.")
    parser.add_argument("--benchmark-data", help="Required for --raw-score-lists; usually eval_benchmark.jsonl.")
    parser.add_argument("--normalized-output", help="Where to write normalized reports when --raw-score-lists is used.")
    parser.add_argument("--summary-output", help="Where to write prepare_summary.json.")
    parser.add_argument("--preflight-output", help="Where to write retry_input_preflight.json.")
    parser.add_argument("--aggregate-by", default="candidate_id")
    parser.add_argument("--atom-threshold", type=float, default=0.9)
    parser.add_argument("--candidate-index", type=int, default=0)
    parser.add_argument("--all-candidates", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--round", dest="round_id", type=int, default=0)
    parser.add_argument("--generator-name", default="qwen-image-2512")
    parser.add_argument("--no-require-initial-plan", action="store_true")
    args = parser.parse_args()

    config = Geneval2RetryPrepareConfig(
        manifest_path=args.manifest,
        package_dir=args.package_dir,
        initial_plan_dir=args.initial_plan_dir,
        diagnostic_jobs_path=args.diagnostic_jobs,
        eval_results_path=args.eval_results,
        raw_score_lists_path=args.raw_score_lists,
        benchmark_data_path=args.benchmark_data,
        normalized_output_path=args.normalized_output,
        summary_path=args.summary_output,
        preflight_output_path=args.preflight_output,
        aggregate_by=args.aggregate_by,
        atom_threshold=args.atom_threshold,
        candidate_index=args.candidate_index,
        all_candidates=args.all_candidates,
        limit=args.limit,
        round_id=args.round_id,
        generator_name=args.generator_name,
        require_initial_plan=not args.no_require_initial_plan,
    )
    summary = prepare_geneval2_retry_inputs(config)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary.get("status") == "ready_for_teacher" else 1


if __name__ == "__main__":
    raise SystemExit(main())
