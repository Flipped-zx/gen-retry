#!/usr/bin/env python3
"""Collect mock visual retry episodes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.collectors.retry_episode_collector import RetryEpisodeCollector
from gen_retry.evaluators.mock_geneval_evaluator import MockGenevalEvaluator
from gen_retry.generators.mock_initial_generator import MockInitialGenerator, MockRetryExecutor
from gen_retry.teachers.mock_teacher import MockTeacher
from gen_retry.utils.ids import make_episode_id
from gen_retry.utils.io import read_jsonl
from gen_retry.utils.logging import log


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect mock Gen-Retry episodes.")
    parser.add_argument("--prompts", default="data/prompts/sample_prompts.jsonl")
    parser.add_argument("--num", type=int, default=5)
    parser.add_argument("--max-retry", type=int, default=2)
    parser.add_argument("--pass-threshold", type=float, default=0.95)
    parser.add_argument("--output-dir", default="data/raw_episodes")
    parser.add_argument("--image-dir", default="data/images")
    args = parser.parse_args()

    records = read_jsonl(args.prompts)[: args.num]
    evaluator = MockGenevalEvaluator(records)
    collector = RetryEpisodeCollector(
        initial_generator=MockInitialGenerator(args.image_dir),
        retry_executor=MockRetryExecutor(args.image_dir),
        evaluator=evaluator,
        teacher=MockTeacher(),
        output_dir=args.output_dir,
    )

    for index, record in enumerate(records):
        prompt = str(record.get("prompt", "")).strip()
        if not prompt:
            raise ValueError(f"{args.prompts} row {index} has empty prompt")
        episode = collector.run_episode(
            prompt,
            max_retry=args.max_retry,
            pass_threshold=args.pass_threshold,
            episode_id=make_episode_id(prompt, index),
            prompt_metadata={key: value for key, value in record.items() if key != "mock_reports"},
        )
        log(f"saved {episode.id}: {episode.final_outcome}")
    log(f"episodes written: {len(records)} -> {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

