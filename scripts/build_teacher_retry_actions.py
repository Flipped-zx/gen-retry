#!/usr/bin/env python3
"""Build teacher retry actions from Geneval diagnostic records."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.data.io import read_json_or_jsonl, write_jsonl
from gen_retry.teacher.build_retry_action import build_teacher_action_row
from gen_retry.teacher.client import TeacherClient
from gen_retry.teacher.schemas import TeacherActionValidationError


def main() -> int:
    parser = argparse.ArgumentParser(description="Build teacher retry-action JSONL.")
    parser.add_argument("--input", default="data/raw/geneval_diagnostics.jsonl")
    parser.add_argument("--output", default="data/processed/teacher_retry_actions.jsonl")
    parser.add_argument("--failed-output", default="data/failed/invalid_teacher_outputs.jsonl")
    parser.add_argument("--dry-run", action="store_true", help="Use deterministic mock teacher actions.")
    args = parser.parse_args()

    records = read_json_or_jsonl(args.input)
    client = None if args.dry_run else TeacherClient()
    ok_rows = []
    failed_rows = []

    for index, record in enumerate(records):
        try:
            ok_rows.append(
                build_teacher_action_row(
                    record,
                    index=index,
                    dry_run=args.dry_run,
                    client=client,
                )
            )
        except TeacherActionValidationError as exc:
            failed_rows.append({"index": index, "record": record, "errors": exc.errors})
        except Exception as exc:
            failed_rows.append({"index": index, "record": record, "errors": [str(exc)]})

    written = write_jsonl(args.output, ok_rows)
    failed_written = write_jsonl(args.failed_output, failed_rows)
    print(f"teacher retry actions written: {written} -> {args.output}")
    print(f"invalid teacher outputs written: {failed_written} -> {args.failed_output}")
    return 0 if ok_rows and not failed_rows else 1 if failed_rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
