#!/usr/bin/env python3
"""Collect real teacher/generator/evaluator episodes through stable adapters."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.collectors.collect_episodes import EpisodeCollector
from gen_retry.evaluators.geneval2_adapter import Geneval2Adapter
from gen_retry.evaluators.geneval_adapter import GenevalAdapter
from gen_retry.generators.real_generator_adapter import RealGeneratorAdapter
from gen_retry.teachers.gpt55_teacher_adapter import GPT55TeacherAdapter
from gen_retry.teachers.seed_teacher_adapter import SeedTeacherAdapter
from gen_retry.utils.ids import make_episode_id
from gen_retry.utils.io import read_jsonl
from gen_retry.utils.logging import log


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect real Gen-Retry planner episodes.")
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--num", type=int, default=0)
    parser.add_argument("--teacher", choices=["gpt55", "seed"], default="gpt55")
    parser.add_argument("--generator", choices=["gpt_image", "gemini_image", "nano"], default="gpt_image")
    parser.add_argument("--evaluator", choices=["geneval", "geneval2"], default="geneval")
    parser.add_argument("--geneval-command-template")
    parser.add_argument("--geneval2-command-template")
    parser.add_argument("--max-retry", type=int, default=2)
    parser.add_argument("--pass-threshold", type=float, default=0.95)
    parser.add_argument("--output-dir", default="data/raw_episodes")
    parser.add_argument("--image-dir", default="data/images")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    records = read_jsonl(args.prompts)
    if args.num:
        records = records[: args.num]
    teacher = GPT55TeacherAdapter() if args.teacher == "gpt55" else SeedTeacherAdapter()
    generator = RealGeneratorAdapter(args.generator)
    evaluator = (
        Geneval2Adapter(args.geneval2_command_template)
        if args.evaluator == "geneval2"
        else GenevalAdapter(args.geneval_command_template)
    )
    collector = EpisodeCollector(
        teacher=teacher,
        generator=generator,
        evaluator=evaluator,
        output_dir=args.output_dir,
        image_dir=args.image_dir,
        resume=args.resume,
    )

    errors = 0
    for index, record in enumerate(records):
        prompt = str(record.get("prompt", "")).strip()
        if not prompt:
            errors += 1
            log(f"skip empty prompt at row {index}")
            continue
        try:
            episode = collector.run_episode(
                prompt,
                evaluator_type=args.evaluator,
                max_retry=args.max_retry,
                pass_threshold=args.pass_threshold,
                episode_id=make_episode_id(prompt, index),
                prompt_metadata={key: value for key, value in record.items() if key != "mock_reports"},
            )
            log(f"saved {episode.episode_id}: {episode.final_outcome}")
        except Exception as exc:  # noqa: BLE001
            errors += 1
            log(f"ERROR row={index} prompt={prompt!r}: {exc}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
