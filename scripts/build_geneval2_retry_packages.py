#!/usr/bin/env python3
"""Build offline GenEval2 retry generation packages from a Qwen manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.offline_package_builder import build_generation_packages_from_manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Convert first-pass Qwen generation manifest rows into offline manual-transfer "
            "generation packages, optionally attaching normalized GenEval2 reports."
        )
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--initial-plan-dir")
    parser.add_argument("--eval-results", help="Normalized GenEval2 JSON/JSONL or atom score rows.")
    parser.add_argument("--benchmark-data", help="Optional GenEval2 benchmark JSONL for official score lists.")
    parser.add_argument("--aggregate-by", default="candidate_id")
    parser.add_argument("--atom-threshold", type=float, default=0.5)
    parser.add_argument(
        "--candidate-index",
        type=int,
        default=0,
        help="Candidate index to package. Default 0 gives one first-pass image per prompt.",
    )
    parser.add_argument("--all-candidates", action="store_true", help="Package every manifest candidate.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--round", dest="round_id", type=int, default=0)
    parser.add_argument("--generator-name", default="qwen-image-2512")
    parser.add_argument(
        "--require-initial-plan",
        action="store_true",
        help="Fail if a selected row cannot be paired with an initial_plan JSON.",
    )
    args = parser.parse_args()

    summary = build_generation_packages_from_manifest(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        initial_plan_dir=args.initial_plan_dir,
        eval_results_path=args.eval_results,
        benchmark_data_path=args.benchmark_data,
        aggregate_by=args.aggregate_by,
        atom_threshold=args.atom_threshold,
        candidate_index=args.candidate_index,
        all_candidates=args.all_candidates,
        limit=args.limit,
        round_id=args.round_id,
        generator_name=args.generator_name,
        require_initial_plan=args.require_initial_plan,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
