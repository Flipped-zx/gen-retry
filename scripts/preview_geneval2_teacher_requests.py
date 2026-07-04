#!/usr/bin/env python3
"""Preview teacher retry requests without calling the teacher API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.teacher_request_preview import (  # noqa: E402
    TeacherRequestPreviewConfig,
    preview_teacher_requests,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build teacher_request JSONL previews from prepared GenEval2 retry packages."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--package-manifest")
    group.add_argument("--package-dir")
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary-output")
    parser.add_argument("--trajectory-dir", help="Optional existing raw trajectory dir for retry-history preview.")
    parser.add_argument("--max-retry", type=int, default=3)
    parser.add_argument("--pass-threshold", type=float, default=0.95)
    parser.add_argument("--no-improvement-patience", type=int, default=1)
    parser.add_argument("--large-regression-score-delta", type=float, default=-0.15)
    parser.add_argument("--allow-retry-after-regression", action="store_true")
    parser.add_argument("--aggregate-by", default="candidate_id")
    parser.add_argument("--atom-threshold", type=float, default=0.9)
    args = parser.parse_args()

    summary = preview_teacher_requests(
        TeacherRequestPreviewConfig(
            package_manifest_path=args.package_manifest,
            package_dir=args.package_dir,
            output_path=args.output,
            summary_path=args.summary_output,
            trajectory_dir=args.trajectory_dir,
            max_retry=args.max_retry,
            pass_threshold=args.pass_threshold,
            no_improvement_patience=args.no_improvement_patience,
            large_regression_score_delta=args.large_regression_score_delta,
            allow_retry_after_regression=args.allow_retry_after_regression,
            aggregate_by=args.aggregate_by,
            atom_threshold=args.atom_threshold,
        )
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
