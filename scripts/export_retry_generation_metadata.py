#!/usr/bin/env python3
"""Export retry-ready trajectories as generation metadata JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.utils.io import write_jsonl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build metadata rows for retry image generation from raw trajectories. "
            "The original GenEval prompt stays in prompt; the teacher retry prompt "
            "is stored in generation_prompt."
        )
    )
    parser.add_argument("--trajectories-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--retry-round", type=int, default=1)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    rows = export_retry_generation_metadata(
        trajectories_dir=Path(args.trajectories_dir),
        retry_round=args.retry_round,
        limit=args.limit,
    )
    count = write_jsonl(args.output, rows)
    print(f"retry generation metadata rows written: {count} -> {args.output}")
    return 0


def export_retry_generation_metadata(
    *,
    trajectories_dir: Path,
    retry_round: int = 1,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    if retry_round <= 0:
        raise ValueError("--retry-round must be positive")
    if not trajectories_dir.exists():
        raise FileNotFoundError(f"trajectories dir does not exist: {trajectories_dir}")

    rows: list[dict[str, Any]] = []
    for path in sorted(trajectories_dir.glob("*.json")):
        trajectory = _read_json(path)
        if trajectory.get("status") != "retry_ready":
            continue
        action = _retry_action(trajectory)
        retry_prompt = str(action.get("retry_prompt", "")).strip()
        if not retry_prompt:
            continue

        prompt_id = str(trajectory.get("prompt_id", "")).strip()
        candidate_id = str(trajectory.get("candidate_id", "")).strip()
        if not prompt_id or not candidate_id:
            raise ValueError(f"{path} missing prompt_id or candidate_id")

        teacher_request = trajectory.get("latest_teacher_request")
        if not isinstance(teacher_request, dict):
            teacher_request = {}
        source = trajectory.get("source")
        if not isinstance(source, dict):
            source = {}

        original_prompt = str(
            teacher_request.get("original_prompt")
            or source.get("original_prompt")
            or source.get("prompt")
            or ""
        ).strip()
        if not original_prompt:
            raise ValueError(f"{path} missing original prompt")

        latest_attempt = _latest_attempt(trajectory)
        seed = _attempt_seed(latest_attempt)
        evaluation = latest_attempt.get("evaluation") if isinstance(latest_attempt, dict) else {}
        if not isinstance(evaluation, dict):
            evaluation = {}

        rows.append(
            {
                "prompt_id": f"{candidate_id}_retry{retry_round:02d}",
                "prompt": original_prompt,
                "generation_prompt": retry_prompt,
                "generation_prompt_source": "teacher_retry_replan",
                "seed": seed,
                "seed_source": "initial_generation",
                "retry_round": retry_round,
                "original_prompt_id": prompt_id,
                "original_candidate_id": candidate_id,
                "source_trajectory_path": str(path),
                "previous_score": evaluation.get("score"),
                "previous_failure_types": list(evaluation.get("critical_failure_types") or []),
            }
        )
        if limit is not None and len(rows) >= limit:
            break

    return rows


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _retry_action(trajectory: dict[str, Any]) -> dict[str, Any]:
    for key in ("retry_ready_action", "latest_teacher_action"):
        value = trajectory.get(key)
        if isinstance(value, dict) and value.get("action_type") == "retry_replan":
            return value
    return {}


def _latest_attempt(trajectory: dict[str, Any]) -> dict[str, Any]:
    attempts = trajectory.get("attempts")
    if isinstance(attempts, list) and attempts and isinstance(attempts[-1], dict):
        return attempts[-1]
    return {}


def _attempt_seed(attempt: dict[str, Any]) -> int | None:
    generation = attempt.get("generation")
    if not isinstance(generation, dict):
        return None
    seed = generation.get("seed")
    if seed is None:
        return None
    try:
        return int(seed)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid generation seed: {seed!r}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
