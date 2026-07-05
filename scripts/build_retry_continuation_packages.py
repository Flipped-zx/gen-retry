#!/usr/bin/env python3
"""Build next-round teacher packages from a GPU GenEval2 handoff."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.exchange import build_retry_continuation_packages  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Convert data/exchange/gpu_to_api/<run>/ into generation packages "
            "that build_geneval2_retry_plans.py can feed to the teacher."
        )
    )
    parser.add_argument("--gpu-handoff-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--round", dest="round_id", type=int)
    parser.add_argument("--trajectory-dir")
    parser.add_argument("--generator-name", default="qwen-image-2512")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    summary = build_retry_continuation_packages(
        gpu_handoff_dir=args.gpu_handoff_dir,
        output_dir=args.output_dir,
        round_id=args.round_id,
        trajectory_dir=args.trajectory_dir,
        generator_name=args.generator_name,
        limit=args.limit,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
