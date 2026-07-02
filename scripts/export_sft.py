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
from gen_retry.export.export_sft import RAW_EPISODE_EXPORT_FORMATS, export_episode_sft


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Gen-Retry SFT rows.")
    parser.add_argument("--input", default="data/raw_episodes")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--format",
        choices=tuple(RAW_EPISODE_EXPORT_FORMATS) + SUPPORTED_EXPORT_FORMATS,
        default="compact",
        help=(
            "Raw episode export: compact, tool, or both. "
            "Legacy processed-row export: qwen, sharegpt, or trl."
        ),
    )
    parser.add_argument("--tool-output", help="Optional tool JSONL path when --format both is used.")
    parser.add_argument("--rejected-output", default="data/rejected/retry_replan_rejected.jsonl")
    args = parser.parse_args()

    if args.format in SUPPORTED_EXPORT_FORMATS:
        rows = read_json_or_jsonl(args.input)
        exported = export_sft_records(rows, args.format)
        written = write_jsonl(args.output, exported)
        print(f"exported {written} {args.format} rows -> {args.output}")
        return 0

    written = export_episode_sft(
        args.input,
        args.output,
        rejected_output=args.rejected_output,
        export_format=args.format,
        tool_output=args.tool_output,
    )
    print(f"exported {written} {args.format} raw episode row(s) -> {args.output}")
    if args.format in {"compact", "both"}:
        print(f"rejected retry rows -> {args.rejected_output}")
    if args.format == "both":
        print(f"tool trajectory rows -> {args.tool_output or 'derived *_tool.jsonl path'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
