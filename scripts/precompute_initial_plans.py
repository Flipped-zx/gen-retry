#!/usr/bin/env python3
"""Precompute and cache teacher initial_plan actions for prompt batches."""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.schemas.actions import InitialPlanAction  # noqa: E402
from gen_retry.teachers.gpt55_teacher_adapter import GPT55TeacherAdapter  # noqa: E402
from gen_retry.teachers.mock_teacher import MockTeacher  # noqa: E402
from gen_retry.utils.io import read_jsonl, write_json  # noqa: E402
from gen_retry.utils.progress import ProgressMeter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Cache teacher initial_plan JSON files.")
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--output-dir", default="data/plans/initial")
    parser.add_argument("--error-dir")
    parser.add_argument("--teacher", choices=["gpt55", "mock"], default="gpt55")
    parser.add_argument("--evaluator-type", default="geneval2")
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--progress-interval", type=float, default=30.0)
    args = parser.parse_args()

    if args.num_workers <= 0:
        raise ValueError("--num-workers must be positive")

    rows = read_jsonl(args.prompts)
    if args.limit is not None:
        rows = rows[: args.limit]
    output_dir = Path(args.output_dir)
    error_dir = Path(args.error_dir) if args.error_dir else output_dir / "_errors"
    output_dir.mkdir(parents=True, exist_ok=True)
    error_dir.mkdir(parents=True, exist_ok=True)

    jobs: list[dict[str, Any]] = []
    skipped = 0
    for index, row in enumerate(rows):
        prompt_id = _prompt_id(row, index)
        output_path = output_dir / f"{prompt_id}.json"
        if args.resume and _valid_plan_cache(output_path):
            skipped += 1
            continue
        jobs.append({"index": index, "row": row, "prompt_id": prompt_id, "output_path": output_path})

    print(
        f"loaded={len(rows)} skipped_valid={skipped} pending={len(jobs)} "
        f"teacher={args.teacher} output_dir={output_dir}",
        flush=True,
    )
    if not jobs:
        return 0

    errors = 0
    progress = ProgressMeter(len(jobs), label="initial-plan", update_interval=args.progress_interval)
    progress.update(completed=0, force=True)
    with ThreadPoolExecutor(max_workers=args.num_workers) as pool:
        futures = {
            pool.submit(
                _plan_one,
                job,
                teacher_name=args.teacher,
                evaluator_type=args.evaluator_type,
                error_dir=error_dir,
            ): job
            for job in jobs
        }
        completed = 0
        for future in as_completed(futures):
            completed += 1
            result = future.result()
            if result.get("status") != "ok":
                errors += 1
            progress.update(
                completed=completed,
                force=args.progress_interval == 0,
                extra=f"errors={errors}",
            )
    print(f"initial_plan complete: ok={len(jobs) - errors} errors={errors}", flush=True)
    return 1 if errors else 0


def _plan_one(
    job: dict[str, Any],
    *,
    teacher_name: str,
    evaluator_type: str,
    error_dir: Path,
) -> dict[str, Any]:
    row = dict(job["row"])
    prompt_id = str(job["prompt_id"])
    output_path = Path(job["output_path"])
    prompt = str(row.get("prompt", "")).strip()
    if not prompt:
        return _record_error(error_dir, prompt_id, row, "ValueError", "empty prompt")
    try:
        teacher = _teacher(teacher_name)
        action = teacher.initial_plan(
            original_prompt=prompt,
            evaluator_type=evaluator_type,
            prompt_metadata={key: value for key, value in row.items() if key != "prompt"},
        )
        action.validate()
        payload = {
            "prompt_id": prompt_id,
            "source_index": row.get("source_index", job.get("index")),
            "original_prompt": prompt,
            "teacher_name": getattr(teacher, "name", teacher.__class__.__name__),
            "evaluator_type": evaluator_type,
            "created_at_unix": time.time(),
            "prompt_metadata": row,
            "initial_plan": action.to_dict(),
        }
        write_json(output_path, payload)
        return {"status": "ok", "prompt_id": prompt_id, "output_path": str(output_path)}
    except Exception as exc:  # noqa: BLE001
        return _record_error(
            error_dir,
            prompt_id,
            row,
            exc.__class__.__name__,
            str(exc),
            traceback_text=traceback.format_exc(limit=8),
        )


def _teacher(name: str):
    if name == "mock":
        return MockTeacher()
    return GPT55TeacherAdapter()


def _valid_plan_cache(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False
        InitialPlanAction.from_dict(dict(data.get("initial_plan") or {}))
        return True
    except Exception:  # noqa: BLE001
        return False


def _record_error(
    error_dir: Path,
    prompt_id: str,
    row: dict[str, Any],
    error_type: str,
    error: str,
    *,
    traceback_text: str = "",
) -> dict[str, Any]:
    payload = {
        "status": "error",
        "prompt_id": prompt_id,
        "prompt": row.get("prompt", ""),
        "source_index": row.get("source_index"),
        "error_type": error_type,
        "error": error,
        "traceback": traceback_text,
        "created_at_unix": time.time(),
    }
    write_json(error_dir / f"{prompt_id}.json", payload)
    return payload


def _prompt_id(row: dict[str, Any], index: int) -> str:
    value = row.get("prompt_id") or row.get("id") or row.get("sample_id")
    if value:
        return _safe_id(str(value))
    import hashlib

    digest = hashlib.sha1(str(row.get("prompt", "")).encode("utf-8")).hexdigest()[:10]
    return f"prompt_{index:05d}_{digest}"


def _safe_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    return safe or "prompt"


if __name__ == "__main__":
    raise SystemExit(main())
