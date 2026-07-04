#!/usr/bin/env python3
"""Check teacher retry-plan package quality."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.quality.retry_plan_quality import (  # noqa: E402
    check_retry_plan_packages,
    load_retry_plan_packages,
)
from gen_retry.utils.io import write_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit retry action packages beyond schema validation.")
    parser.add_argument("inputs", nargs="+", help="Retry package JSON files, globs, or retry_action_manifest.jsonl.")
    parser.add_argument("--output", help="Optional JSON report path.")
    parser.add_argument("--fail-on-warning", action="store_true")
    args = parser.parse_args()

    packages = load_retry_plan_packages(args.inputs)
    report = check_retry_plan_packages(packages)
    if args.output:
        write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if report["critical_count"]:
        return 1
    if args.fail_on_warning and report["warning_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
