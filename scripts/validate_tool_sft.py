#!/usr/bin/env python3
"""Validate Gen-Retry tool trajectory SFT JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.export.export_sft import validate_tool_trajectory_row  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate tool-call trajectory SFT rows.")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()

    total = 0
    errors = 0
    for path_text in args.paths:
        path = Path(path_text)
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            total += 1
            row = json.loads(line)
            row_errors = validate_tool_trajectory_row(row)
            if row_errors:
                errors += 1
                print(f"FAIL {path}:{lineno}: {row_errors}")
    print(f"validated tool rows: {total}; rows with errors: {errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
