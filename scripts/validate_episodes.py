#!/usr/bin/env python3
"""Validate raw visual retry episodes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.filters.validate_episode import validate_episode_dict
from gen_retry.utils.io import read_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate retry episode JSON files.")
    parser.add_argument("episodes_dir", nargs="?", default="data/raw_episodes")
    parser.add_argument("--strict-images", action="store_true", help="Require real image files.")
    args = parser.parse_args()

    root = Path(args.episodes_dir)
    files = sorted(root.glob("*.json"))
    if not files:
        print(f"no episode JSON files found in {root}")
        return 1
    total_errors = 0
    for path in files:
        errors = validate_episode_dict(read_json(path), mock_mode=not args.strict_images)
        if errors:
            total_errors += len(errors)
            for error in errors:
                print(f"{path}: {error}")
        else:
            print(f"PASS {path}")
    print(f"episodes: {len(files)}")
    print(f"errors: {total_errors}")
    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

