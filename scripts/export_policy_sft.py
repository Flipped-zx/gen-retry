#!/usr/bin/env python3
"""Export policy-only SFT rows from raw retry episodes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.export.export_policy_sft import export_policy_sft


def main() -> int:
    parser = argparse.ArgumentParser(description="Export policy-only retry SFT.")
    parser.add_argument("--episodes-dir", default="data/raw_episodes")
    parser.add_argument("--output", default="data/sft/retry_policy_sft_sharegpt.jsonl")
    parser.add_argument("--include-partial", action="store_true")
    parser.add_argument("--include-negative", action="store_true")
    args = parser.parse_args()

    count = export_policy_sft(
        args.episodes_dir,
        args.output,
        include_partial=args.include_partial,
        include_negative=args.include_negative,
    )
    print(f"policy SFT rows written: {count} -> {args.output}")
    return 0 if count else 1


if __name__ == "__main__":
    raise SystemExit(main())

