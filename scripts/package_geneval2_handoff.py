#!/usr/bin/env python3
"""Package lightweight GPU GenEval2 outputs for Git sync back to the API machine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.exchange import package_gpu_to_api_handoff  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a gpu_to_api GenEval2 handoff directory.")
    parser.add_argument("--generation-manifest", required=True)
    parser.add_argument("--geneval2-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--include-atom-rows", action="store_true")
    args = parser.parse_args()

    summary = package_gpu_to_api_handoff(
        generation_manifest_path=args.generation_manifest,
        geneval2_dir=args.geneval2_dir,
        output_dir=args.output_dir,
        expected_count=args.expected_count,
        include_atom_rows=args.include_atom_rows,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
