#!/usr/bin/env python3
"""Preflight-check GenEval2 retry inputs before teacher API calls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.quality.geneval2_retry_inputs import check_geneval2_retry_inputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check package manifest, diagnostic jobs, and normalized GenEval2 reports for retry planning."
    )
    parser.add_argument("--package-manifest", required=True)
    parser.add_argument("--diagnostic-jobs")
    parser.add_argument("--eval-results")
    parser.add_argument("--expected-count", type=int, default=100)
    parser.add_argument("--output")
    parser.add_argument("--fail-on-warning", action="store_true")
    args = parser.parse_args()

    report = check_geneval2_retry_inputs(
        package_manifest_path=args.package_manifest,
        diagnostic_jobs_path=args.diagnostic_jobs,
        eval_results_path=args.eval_results,
        expected_count=args.expected_count,
        output_path=args.output,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if report["critical_count"]:
        return 1
    if args.fail_on_warning and report["warning_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
