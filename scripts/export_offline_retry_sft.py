#!/usr/bin/env python3
"""Export SFT rows from offline candidate-level retry trajectories."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.export.export_offline_sft import export_offline_retry_sft  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export retry_replan SFT JSONL from offline raw trajectory JSON files."
    )
    parser.add_argument("--trajectories-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rejected-output")
    parser.add_argument(
        "--include-image-refs",
        action="store_true",
        help="Keep local image_path/image_id artifact references in the user context.",
    )
    args = parser.parse_args()

    count = export_offline_retry_sft(
        args.trajectories_dir,
        args.output,
        rejected_output=args.rejected_output,
        include_image_refs=args.include_image_refs,
    )
    print(f"offline retry SFT rows written: {count} -> {args.output}")
    if args.rejected_output:
        print(f"rejected trajectories -> {args.rejected_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
