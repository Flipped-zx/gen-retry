#!/usr/bin/env python3
"""Collect mock Geneval/Geneval2-guided regeneration episodes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.collectors.collect_episodes import EpisodeCollector
from gen_retry.evaluators.mock_geneval import MockGenevalEvaluator
from gen_retry.generators.mock_generator import MockGenerator
from gen_retry.teachers.gpt55_teacher_adapter import GPT55TeacherAdapter
from gen_retry.teachers.mock_teacher import MockTeacher
from gen_retry.teachers.seed_teacher_adapter import SeedTeacherAdapter
from gen_retry.utils.ids import make_episode_id
from gen_retry.utils.io import read_jsonl
from gen_retry.utils.logging import log


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect mock Gen-Retry planner episodes.")
    parser.add_argument("--prompts", default="data/prompts/sample_prompts.jsonl")
    parser.add_argument("--num", type=int, default=5)
    parser.add_argument("--teacher", choices=["mock", "gpt55", "seed"], default="mock")
    parser.add_argument("--evaluator-type", choices=["geneval", "geneval2"], default="geneval")
    parser.add_argument("--max-retry", type=int, default=2)
    parser.add_argument("--pass-threshold", type=float, default=0.95)
    parser.add_argument("--output-dir", default="data/raw_episodes")
    parser.add_argument("--image-dir", default="data/images")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    records = read_jsonl(args.prompts)[: args.num]
    if args.teacher == "gpt55":
        teacher = GPT55TeacherAdapter()
    elif args.teacher == "seed":
        teacher = SeedTeacherAdapter()
    else:
        teacher = MockTeacher()
    evaluator = MockGenevalEvaluator(records, evaluator_type=args.evaluator_type)
    collector = EpisodeCollector(
        teacher=teacher,
        generator=MockGenerator(),
        evaluator=evaluator,
        output_dir=args.output_dir,
        image_dir=args.image_dir,
        resume=args.resume,
    )

    saved = 0
    for index, record in enumerate(records):
        prompt = str(record.get("prompt", "")).strip()
        if not prompt:
            raise ValueError(f"{args.prompts} row {index} has empty prompt")
        episode = collector.run_episode(
            prompt,
            evaluator_type=args.evaluator_type,
            max_retry=args.max_retry,
            pass_threshold=args.pass_threshold,
            episode_id=make_episode_id(prompt, index),
            prompt_metadata={key: value for key, value in record.items() if key != "mock_reports"},
        )
        saved += 1
        log(f"saved {episode.episode_id}: {episode.final_outcome}")
    log(f"episodes written: {saved} -> {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
