#!/usr/bin/env python3
"""Export Gen-Retry SFT JSONL into downstream chat fine-tuning formats."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.data.exporters import SUPPORTED_EXPORT_FORMATS, export_sft_records
from gen_retry.data.io import read_json_or_jsonl, write_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Gen-Retry SFT rows.")
    parser.add_argument("--input", default="data/processed/geneval_retry_sft_5_full.jsonl")
    parser.add_argument("--output", required=True)
    parser.add_argument("--format", choices=SUPPORTED_EXPORT_FORMATS, required=True)
    args = parser.parse_args()

    rows = read_json_or_jsonl(args.input)
    exported = export_sft_records(rows, args.format)
    written = write_jsonl(args.output, exported)
    print(f"exported {written} {args.format} rows -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
