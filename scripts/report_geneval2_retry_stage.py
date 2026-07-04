#!/usr/bin/env python3
"""Write the GenEval2 balanced-100 retry-stage audit report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.geneval2_retry_report import (  # noqa: E402
    DEFAULT_DIAGNOSTIC_JOBS,
    DEFAULT_EVAL_RESULTS,
    DEFAULT_INITIAL_PLAN_DIR,
    DEFAULT_MANIFEST,
    DEFAULT_PACKAGE_MANIFEST,
    DEFAULT_PROMPTS,
    DEFAULT_RETRY_MANIFEST,
    DEFAULT_SFT_OUTPUT,
    DEFAULT_TRAJECTORY_DIR,
    RetryStageReportConfig,
    build_retry_stage_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Chinese markdown and JSON summary for the GenEval2 retry stage."
    )
    parser.add_argument("--prompts", default=DEFAULT_PROMPTS)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--initial-plan-dir", default=DEFAULT_INITIAL_PLAN_DIR)
    parser.add_argument("--package-manifest", default=DEFAULT_PACKAGE_MANIFEST)
    parser.add_argument("--diagnostic-jobs", default=DEFAULT_DIAGNOSTIC_JOBS)
    parser.add_argument("--eval-results", default=DEFAULT_EVAL_RESULTS)
    parser.add_argument("--raw-score-lists")
    parser.add_argument("--benchmark-data")
    parser.add_argument("--retry-manifest", default=DEFAULT_RETRY_MANIFEST)
    parser.add_argument("--trajectory-dir", default=DEFAULT_TRAJECTORY_DIR)
    parser.add_argument("--sft-output", default=DEFAULT_SFT_OUTPUT)
    parser.add_argument("--candidate-index", type=int, default=0)
    parser.add_argument("--all-candidates", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--atom-threshold", type=float, default=0.9)
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary-output")
    args = parser.parse_args()

    result = build_retry_stage_report(
        RetryStageReportConfig(
            prompts_path=args.prompts,
            manifest_path=args.manifest,
            initial_plan_dir=args.initial_plan_dir,
            package_manifest_path=args.package_manifest,
            diagnostic_jobs_path=args.diagnostic_jobs,
            eval_results_path=args.eval_results,
            raw_score_lists_path=args.raw_score_lists,
            benchmark_data_path=args.benchmark_data,
            retry_manifest_path=args.retry_manifest,
            trajectory_dir=args.trajectory_dir,
            sft_output_path=args.sft_output,
            candidate_index=args.candidate_index,
            all_candidates=args.all_candidates,
            limit=args.limit,
            atom_threshold=args.atom_threshold,
            markdown_output_path=args.markdown_output,
            summary_output_path=args.summary_output,
        )
    )
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
