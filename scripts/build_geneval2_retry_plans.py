#!/usr/bin/env python3
"""Build GenEval2 retry plans from first-pass packages and diagnostics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.retry_plan_batch import (  # noqa: E402
    RetryPlanBatchConfig,
    run_retry_plan_batch,
    teacher_from_name,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Attach GenEval2 diagnostics to Qwen first-pass packages, then call "
            "the retry teacher to write retry action packages."
        )
    )
    parser.add_argument("--manifest", help="Qwen generation_manifest.jsonl. If supplied, packages are rebuilt first.")
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--trajectory-dir", required=True)
    parser.add_argument("--initial-plan-dir")
    parser.add_argument("--eval-results", help="Normalized GenEval2 JSON/JSONL or atom score rows.")
    parser.add_argument("--diagnostic-jobs", help="Optional diagnostic_jobs.jsonl used for candidate coverage preflight.")
    parser.add_argument("--benchmark-data", help="Optional GenEval2 benchmark JSONL for score-list joining.")
    parser.add_argument("--aggregate-by", default="candidate_id")
    parser.add_argument("--atom-threshold", type=float, default=0.5)
    parser.add_argument("--candidate-index", type=int, default=0)
    parser.add_argument("--all-candidates", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--round", dest="round_id", type=int, default=0)
    parser.add_argument("--generator-name", default="qwen-image-2512")
    parser.add_argument("--teacher", choices=["gpt55", "seed", "mock"], default="gpt55")
    parser.add_argument("--max-retry", type=int, default=3)
    parser.add_argument("--pass-threshold", type=float, default=0.95)
    parser.add_argument("--no-improvement-patience", type=int, default=1)
    parser.add_argument("--large-regression-score-delta", type=float, default=-0.15)
    parser.add_argument("--allow-retry-after-regression", action="store_true")
    parser.add_argument("--allow-missing-eval", action="store_true")
    parser.add_argument("--no-require-initial-plan", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    if args.manifest and not args.eval_results and not args.allow_missing_eval:
        raise ValueError("--eval-results is required with --manifest unless --allow-missing-eval is set")

    config = RetryPlanBatchConfig(
        manifest_path=args.manifest,
        package_dir=args.package_dir,
        output_dir=args.output_dir,
        trajectory_dir=args.trajectory_dir,
        initial_plan_dir=args.initial_plan_dir,
        eval_results_path=args.eval_results,
        diagnostic_jobs_path=args.diagnostic_jobs,
        benchmark_data_path=args.benchmark_data,
        aggregate_by=args.aggregate_by,
        atom_threshold=args.atom_threshold,
        candidate_index=args.candidate_index,
        all_candidates=args.all_candidates,
        limit=args.limit,
        round_id=args.round_id,
        generator_name=args.generator_name,
        require_initial_plan=not args.no_require_initial_plan,
        allow_missing_eval=args.allow_missing_eval,
        resume=args.resume,
        max_retry=args.max_retry,
        pass_threshold=args.pass_threshold,
        no_improvement_patience=args.no_improvement_patience,
        large_regression_score_delta=args.large_regression_score_delta,
        allow_retry_after_regression=args.allow_retry_after_regression,
    )
    summary = run_retry_plan_batch(config, teacher=teacher_from_name(args.teacher))
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
