#!/usr/bin/env python3
"""Rebuild retry_action_manifest.jsonl from retry action package files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.quality.retry_plan_quality import check_retry_plan_packages  # noqa: E402
from gen_retry.utils.io import read_json, write_json, write_jsonl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild retry action manifest and quality report from package files."
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--manifest-output")
    parser.add_argument("--quality-output")
    parser.add_argument("--summary-output")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    manifest_output = Path(args.manifest_output) if args.manifest_output else output_dir / "retry_action_manifest.jsonl"
    quality_output = Path(args.quality_output) if args.quality_output else output_dir / "retry_plan_quality_report.json"
    summary_output = Path(args.summary_output) if args.summary_output else output_dir / "manifest_rebuild_summary.json"

    rows: list[dict[str, Any]] = []
    quality_packages: list[tuple[str, dict[str, Any]]] = []
    issues: list[str] = []
    seen: set[str] = set()
    duplicate_ids: set[str] = set()

    for path in sorted(output_dir.glob("*_retry_action_package.json")):
        try:
            payload = read_json(path)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"unreadable package {path}: {exc}")
            continue
        candidate_id = str(payload.get("candidate_id", "")).strip()
        if not candidate_id:
            issues.append(f"missing candidate_id in {path}")
            continue
        if candidate_id in seen:
            duplicate_ids.add(candidate_id)
        seen.add(candidate_id)
        quality_packages.append((str(path), payload))
        rows.append(
            {
                "package_path": str(payload.get("package_path", "")),
                "output_path": str(path),
                "trajectory_path": str(payload.get("trajectory_path", "")),
                "trajectory_id": str(payload.get("trajectory_id", "")),
                "prompt_id": str(payload.get("prompt_id", "")),
                "candidate_id": candidate_id,
                "round": payload.get("round", 0),
                "stop": payload.get("stop", {}),
                "status": str(payload.get("status", "")),
                "has_teacher_request": isinstance(payload.get("teacher_request"), dict),
                "has_teacher_action": isinstance(payload.get("teacher_action"), dict),
                "teacher_error": str(payload.get("teacher_error", "")),
            }
        )

    if duplicate_ids:
        issues.append(f"duplicate candidate_id(s): {sorted(duplicate_ids)[:20]}")
    if args.expected_count is not None and len(rows) != args.expected_count:
        issues.append(f"manifest row count {len(rows)} != expected {args.expected_count}")

    rows.sort(key=lambda row: str(row.get("candidate_id", "")))
    write_jsonl(manifest_output, rows)
    quality_report = check_retry_plan_packages(quality_packages)
    write_json(quality_output, quality_report)
    summary = {
        "status": "error" if issues or quality_report.get("critical_count") else "ok",
        "output_dir": str(output_dir),
        "manifest_output": str(manifest_output),
        "quality_output": str(quality_output),
        "packages": len(rows),
        "expected_count": args.expected_count,
        "quality_status": quality_report.get("status"),
        "quality_critical_count": quality_report.get("critical_count"),
        "quality_warning_count": quality_report.get("warning_count"),
        "issues": issues,
    }
    write_json(summary_output, summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
