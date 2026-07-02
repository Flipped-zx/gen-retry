#!/usr/bin/env python3
"""Generate Qwen-Image candidates and save structured Geneval diagnostics.

This script is safe to import locally. Real generation/evaluation only happens
when command templates are supplied and --plan-only is not set.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.collectors.qwen_geneval_batch import QwenGenevalBatchCollector


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Qwen-Image + Geneval diagnostics.")
    parser.add_argument("--prompts", required=True, help="Prompt JSONL with prompt/category/expected fields.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--images-per-prompt", type=int, default=4)
    parser.add_argument("--gpus", default="0,1,2,3", help="Comma-separated GPU ids.")
    parser.add_argument("--base-seed", type=int, default=1000)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--run-id")
    parser.add_argument(
        "--qwen-model-path",
        default="/home/develop/biocloudplantform/xxr/models/Qwen-Image-2512",
        help="Local Qwen-Image model path available on the generation server.",
    )
    parser.add_argument("--plan-only", action="store_true", help="Only write generation_manifest.jsonl.")
    parser.add_argument("--skip-generation", action="store_true")
    parser.add_argument("--skip-geneval", action="store_true")
    parser.add_argument("--allow-missing-images", action="store_true")
    parser.add_argument("--generator-name", default="qwen-image")
    parser.add_argument(
        "--progress-interval",
        type=float,
        default=30.0,
        help="Seconds between total progress/ETA updates. Use 0 to print every job.",
    )
    parser.add_argument(
        "--generation-command-template",
        help=(
            "Shell command template. Variables include {prompt}, {image_path}, "
            "{seed}, {candidate_id}, {gpu}. Values are shell-quoted."
        ),
    )
    parser.add_argument(
        "--geneval-command-template",
        help=(
            "Shell command template. Variables include {prompt}, {image_path}, "
            "{geneval_output_path}, {candidate_id}, {gpu}. Values are shell-quoted. "
            "The command may write JSON to {geneval_output_path} or print JSON to stdout."
        ),
    )
    args = parser.parse_args()

    gpus = [item.strip() for item in args.gpus.split(",") if item.strip()]
    if not gpus:
        raise ValueError("--gpus must contain at least one GPU id")

    collector = QwenGenevalBatchCollector(
        prompts_path=args.prompts,
        output_dir=args.output_dir,
        images_per_prompt=args.images_per_prompt,
        gpus=gpus,
        base_seed=args.base_seed,
        run_id=args.run_id,
        qwen_model_path=args.qwen_model_path,
    )
    jobs = collector.plan_jobs(limit=args.limit)
    manifest = collector.write_manifest(jobs)
    print(f"planned candidates: {len(jobs)} -> {manifest}")

    if args.plan_only:
        print("plan-only mode: generation and Geneval were not run")
        return 0

    if not args.skip_generation:
        if not args.generation_command_template:
            raise ValueError("--generation-command-template is required unless --skip-generation is set")
        failures = collector.run_generation(
            jobs,
            command_template=args.generation_command_template,
            allow_missing_images=args.allow_missing_images,
            progress_interval=args.progress_interval,
        )
        print(f"generation failures: {len(failures)}")
        if failures:
            return 1

    if not args.skip_geneval:
        if not args.geneval_command_template:
            raise ValueError("--geneval-command-template is required unless --skip-geneval is set")
        failures = collector.run_geneval(
            jobs,
            command_template=args.geneval_command_template,
            progress_interval=args.progress_interval,
        )
        print(f"Geneval failures: {len(failures)}")
        if failures:
            return 1

    diagnostics_path, teacher_path = collector.normalize_outputs(
        jobs,
        generator_name=args.generator_name,
    )
    print(f"candidate diagnostics: {diagnostics_path}")
    print(f"teacher diagnostics: {teacher_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
