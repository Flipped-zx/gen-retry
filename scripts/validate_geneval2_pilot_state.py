#!/usr/bin/env python3
"""Validate GenEval2/Qwen pilot artifacts without running GPU work."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.schemas.actions import InitialPlanAction  # noqa: E402
from gen_retry.schemas.reports import NormalizedEvalReport  # noqa: E402
from gen_retry.utils.io import write_json  # noqa: E402


REQUIRED_PROMPT_FIELDS = {
    "prompt_id",
    "source_index",
    "prompt",
    "skills",
    "atom_count",
    "vqa_list",
    "sampling_bucket",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate GenEval2 pilot prompts/images/plans/eval reports.")
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--image-dir")
    parser.add_argument("--manifest")
    parser.add_argument("--plan-dir")
    parser.add_argument("--geneval2-reports")
    parser.add_argument("--run-log")
    parser.add_argument("--expected-prompts", type=int, default=100)
    parser.add_argument("--images-per-prompt", type=int, default=5)
    parser.add_argument("--allow-partial-images", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    summary: dict[str, Any] = {
        "status": "ok",
        "errors": [],
        "warnings": [],
    }
    prompts = _validate_prompts(Path(args.prompts), args.expected_prompts, summary)
    expected_images = len(prompts) * args.images_per_prompt
    summary["expected_images"] = expected_images
    if args.image_dir:
        _validate_image_layout(
            Path(args.image_dir),
            prompts,
            images_per_prompt=args.images_per_prompt,
            allow_partial=args.allow_partial_images,
            summary=summary,
        )
    if args.manifest:
        _validate_manifest(Path(args.manifest), expected_images, summary)
    if args.plan_dir:
        _validate_plan_dir(Path(args.plan_dir), prompts, summary)
    if args.geneval2_reports:
        _validate_geneval2_reports(Path(args.geneval2_reports), summary)
    if args.run_log:
        summary["latest_progress"] = _latest_progress(Path(args.run_log))

    if summary["errors"]:
        summary["status"] = "error"
    elif summary["warnings"]:
        summary["status"] = "warning"

    if args.output:
        write_json(args.output, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if summary["errors"] else 0


def _validate_prompts(path: Path, expected_prompts: int, summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _read_jsonl(path)
    summary["prompt_rows"] = len(rows)
    if len(rows) != expected_prompts:
        summary["errors"].append(f"prompt row count {len(rows)} != expected {expected_prompts}")
    seen_ids: set[str] = set()
    for index, row in enumerate(rows):
        missing = sorted(REQUIRED_PROMPT_FIELDS - set(row))
        if missing:
            summary["errors"].append(f"prompt row {index} missing fields: {missing}")
        prompt_id = str(row.get("prompt_id", "")).strip()
        if not prompt_id:
            summary["errors"].append(f"prompt row {index} has empty prompt_id")
        if prompt_id in seen_ids:
            summary["errors"].append(f"duplicate prompt_id: {prompt_id}")
        seen_ids.add(prompt_id)
        if not str(row.get("prompt", "")).strip():
            summary["errors"].append(f"prompt row {index} has empty prompt")
        if not isinstance(row.get("skills"), list):
            summary["errors"].append(f"prompt row {index} skills must be a list")
        if not isinstance(row.get("vqa_list"), list):
            summary["errors"].append(f"prompt row {index} vqa_list must be a list")
    return rows


def _validate_image_layout(
    image_dir: Path,
    prompts: list[dict[str, Any]],
    *,
    images_per_prompt: int,
    allow_partial: bool,
    summary: dict[str, Any],
) -> None:
    missing: list[dict[str, Any]] = []
    existing = 0
    for prompt_index, row in enumerate(prompts):
        prompt_id = str(row.get("prompt_id", f"{prompt_index:05d}"))
        for candidate_index in range(images_per_prompt):
            path = image_dir / f"{prompt_index:05d}" / "samples" / f"{candidate_index:05d}.png"
            if path.exists():
                existing += 1
            else:
                missing.append(
                    {
                        "prompt_index": prompt_index,
                        "prompt_id": prompt_id,
                        "candidate_index": candidate_index,
                        "image_path": str(path),
                    }
                )
    summary["image_layout"] = {
        "image_dir": str(image_dir),
        "existing": existing,
        "missing": len(missing),
        "missing_examples": missing[:10],
    }
    if missing and not allow_partial:
        summary["errors"].append(f"missing {len(missing)} image(s) under {image_dir}")
    elif missing:
        summary["warnings"].append(f"partial image layout: missing {len(missing)} image(s)")


def _validate_manifest(path: Path, expected_images: int, summary: dict[str, Any]) -> None:
    rows = _read_jsonl(path)
    candidate_ids = [str(row.get("candidate_id", "")) for row in rows]
    duplicates = sorted({item for item in candidate_ids if candidate_ids.count(item) > 1 and item})
    summary["manifest"] = {
        "path": str(path),
        "rows": len(rows),
        "duplicate_candidate_ids": duplicates[:10],
    }
    if len(rows) != expected_images:
        summary["errors"].append(f"manifest row count {len(rows)} != expected {expected_images}")
    if duplicates:
        summary["errors"].append(f"manifest has duplicate candidate_ids: {duplicates[:10]}")
    for index, row in enumerate(rows[: expected_images or len(rows)]):
        for key in ("candidate_id", "candidate_index", "prompt", "image_path", "seed"):
            if key not in row:
                summary["errors"].append(f"manifest row {index} missing {key}")


def _validate_plan_dir(plan_dir: Path, prompts: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    missing = 0
    invalid = 0
    existing = 0
    for row in prompts:
        prompt_id = str(row.get("prompt_id", "")).strip()
        if not prompt_id:
            continue
        path = plan_dir / f"{_safe_id(prompt_id)}.json"
        if not path.exists():
            missing += 1
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("plan cache root must be an object")
            InitialPlanAction.from_dict(dict(data.get("initial_plan") or {}))
            existing += 1
        except Exception as exc:  # noqa: BLE001
            invalid += 1
            summary["errors"].append(f"invalid initial plan cache {path}: {exc}")
    summary["initial_plans"] = {
        "plan_dir": str(plan_dir),
        "existing": existing,
        "missing": missing,
        "invalid": invalid,
    }
    if missing:
        summary["warnings"].append(f"initial plan cache missing for {missing} prompt(s)")


def _validate_geneval2_reports(path: Path, summary: dict[str, Any]) -> None:
    rows = _read_jsonl(path)
    invalid = 0
    missing_prompt = 0
    missing_image = 0
    for index, row in enumerate(rows):
        try:
            report = NormalizedEvalReport.from_dict(dict(row.get("normalized_report") or {}))
            report.to_dict()
        except Exception as exc:  # noqa: BLE001
            invalid += 1
            summary["errors"].append(f"invalid normalized report row {index}: {exc}")
        if not str(row.get("prompt", "")).strip():
            missing_prompt += 1
        image_path = str(row.get("image_path", "")).strip()
        if not image_path or not Path(image_path).exists():
            missing_image += 1
    summary["geneval2_reports"] = {
        "path": str(path),
        "rows": len(rows),
        "invalid": invalid,
        "missing_prompt": missing_prompt,
        "missing_or_absent_images": missing_image,
    }
    if missing_prompt:
        summary["warnings"].append(f"{missing_prompt} report row(s) have empty prompt")
    if missing_image:
        summary["warnings"].append(f"{missing_image} report row(s) reference missing image paths")


def _latest_progress(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"run_log": str(path), "found": False}
    latest: dict[str, Any] = {"run_log": str(path), "found": False}
    pattern = re.compile(
        r"\[qwen-geneval (?P<kind>shard|total)[^\]]*\].*?"
        r"(?P<completed>\d+)/(?P<total>\d+).*?eta=(?P<eta>.*?)\s+rate=(?P<rate>[0-9.]+)/s"
    )
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r", "\n")
    by_kind: dict[str, dict[str, Any]] = {}
    for line in text.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        parsed = {
            "run_log": str(path),
            "found": True,
            "kind": match.group("kind"),
            "completed": int(match.group("completed")),
            "total": int(match.group("total")),
            "eta": match.group("eta"),
            "rate_per_second": float(match.group("rate")),
            "line": line.strip(),
        }
        latest = parsed
        by_kind[str(parsed["kind"])] = parsed
    if by_kind:
        preferred = by_kind.get("shard") or latest
        result = dict(preferred)
        result["by_kind"] = by_kind
        return result
    return latest


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError(f"{path}:{lineno} is not a JSON object")
        rows.append(item)
    return rows


def _safe_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    return safe or "prompt"


if __name__ == "__main__":
    raise SystemExit(main())
