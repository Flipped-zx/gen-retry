#!/usr/bin/env python3
"""Export Gen-Retry SFT JSONL."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.data.exporters import SUPPORTED_EXPORT_FORMATS, export_sft_records
from gen_retry.data.io import read_json_or_jsonl, write_jsonl
from gen_retry.export.export_sft import export_episode_sft


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Gen-Retry SFT rows.")
    parser.add_argument("--input", default="data/raw_episodes")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--format",
        choices=SUPPORTED_EXPORT_FORMATS,
        help="Legacy export format for processed SFT rows. Omit for raw episode ShareGPT export.",
    )
    parser.add_argument("--rejected-output", default="data/rejected/retry_replan_rejected.jsonl")
    args = parser.parse_args()

    if args.format:
        rows = read_json_or_jsonl(args.input)
        exported = export_sft_records(rows, args.format)
        written = write_jsonl(args.output, exported)
        print(f"exported {written} {args.format} rows -> {args.output}")
        return 0

    written = export_episode_sft(args.input, args.output, rejected_output=args.rejected_output)
    print(f"exported {written} ShareGPT rows -> {args.output}")
    print(f"rejected retry rows -> {args.rejected_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
