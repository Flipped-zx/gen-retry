#!/usr/bin/env python3
"""Validate offline manual-transfer packages and raw retry trajectories."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.offline_planner import validate_offline_object


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Machine A input packages, Machine B retry action packages, or raw trajectories."
    )
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--base-dir", help="Base directory for resolving relative image paths.")
    args = parser.parse_args()

    total_errors = 0
    for path_text in args.paths:
        path = Path(path_text)
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            print(f"{path}: top-level JSON must be an object", file=sys.stderr)
            total_errors += 1
            continue
        base_dir = Path(args.base_dir) if args.base_dir else path.parent
        errors = validate_offline_object(data, base_dir=base_dir)
        if errors:
            total_errors += len(errors)
            print(f"{path}: FAIL")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"{path}: ok")
    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
