#!/usr/bin/env python3
"""Run official GenEval and select teacher-ready retry diagnostics."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.data.io import read_json_or_jsonl, write_jsonl  # noqa: E402
from gen_retry.evaluators.official_geneval_adapter import (  # noqa: E402
    official_result_to_candidate_row,
)
from gen_retry.filters.geneval_selection import (  # noqa: E402
    select_teacher_candidates,
    teacher_rows_from_selected,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate Qwen-Image GenEval samples and select retry teacher inputs."
    )
    parser.add_argument("--image-dir", required=True, help="Directory in official GenEval image layout.")
    parser.add_argument(
        "--geneval-dir",
        default="../geneval",
        help="Path to the official GenEval repo directory.",
    )
    parser.add_argument(
        "--object-detector-path",
        required=True,
        help="Folder containing the Mask2Former checkpoint downloaded by GenEval.",
    )
    parser.add_argument("--model-config", help="Optional mmdet config path.")
    parser.add_argument(
        "--geneval-option",
        action="append",
        default=[],
        help="Extra GenEval --options item, e.g. threshold=0.3. May be repeated.",
    )
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--results-jsonl", help="Official GenEval results JSONL path.")
    parser.add_argument("--output-dir", help="Directory for gen-retry converted outputs.")
    parser.add_argument("--min-prompt-score", type=float, default=0.25)
    parser.add_argument("--max-prompt-score", type=float, default=0.75)
    parser.add_argument(
        "--candidate-policy",
        choices=["failed", "all", "best_failed", "worst_failed"],
        default="failed",
        help="Which candidates from selected prompts are sent to GPT teacher.",
    )
    parser.add_argument("--max-teacher-rows", type=int)
    parser.add_argument("--generator-name", default="qwen-image")
    args = parser.parse_args()

    image_dir = Path(args.image_dir)
    output_dir = Path(args.output_dir) if args.output_dir else image_dir.parent / "geneval_selected"
    output_dir.mkdir(parents=True, exist_ok=True)
    results_jsonl = Path(args.results_jsonl) if args.results_jsonl else output_dir / "geneval_results.jsonl"

    if not args.skip_eval:
        run_official_geneval(
            geneval_dir=Path(args.geneval_dir),
            image_dir=image_dir,
            outfile=results_jsonl,
            object_detector_path=Path(args.object_detector_path),
            model_config=args.model_config,
            options=args.geneval_option,
        )

    results = read_json_or_jsonl(results_jsonl)
    candidates = [
        official_result_to_candidate_row(
            row,
            index=index,
            generator_metadata={"generator": args.generator_name},
        )
        for index, row in enumerate(results)
    ]
    selected_candidates, prompt_rows = select_teacher_candidates(
        candidates,
        min_score=args.min_prompt_score,
        max_score=args.max_prompt_score,
        candidate_policy=args.candidate_policy,
        max_rows=args.max_teacher_rows,
    )
    teacher_rows = teacher_rows_from_selected(selected_candidates)

    write_jsonl(output_dir / "candidate_diagnostics.jsonl", candidates)
    write_jsonl(output_dir / "prompt_selection.jsonl", prompt_rows)
    write_jsonl(output_dir / "selected_candidate_diagnostics.jsonl", selected_candidates)
    write_jsonl(output_dir / "teacher_diagnostics.selected.jsonl", teacher_rows)

    selected_prompts = sum(1 for row in prompt_rows if row.get("selected") is True)
    print(f"[geneval-select] official results: {len(results)} -> {results_jsonl}")
    print(f"[geneval-select] candidates: {len(candidates)} -> {output_dir / 'candidate_diagnostics.jsonl'}")
    print(f"[geneval-select] selected prompts: {selected_prompts} -> {output_dir / 'prompt_selection.jsonl'}")
    print(
        "[geneval-select] selected teacher rows: "
        f"{len(teacher_rows)} -> {output_dir / 'teacher_diagnostics.selected.jsonl'}"
    )
    return 0


def run_official_geneval(
    *,
    geneval_dir: Path,
    image_dir: Path,
    outfile: Path,
    object_detector_path: Path,
    model_config: str | None,
    options: list[str],
) -> None:
    script = geneval_dir / "evaluation" / "evaluate_images.py"
    if not script.exists():
        raise FileNotFoundError(f"GenEval evaluator not found: {script}")
    cmd = [
        sys.executable,
        str(script),
        str(image_dir),
        "--outfile",
        str(outfile),
        "--model-path",
        str(object_detector_path),
    ]
    if model_config:
        cmd.extend(["--model-config", model_config])
    if options:
        cmd.append("--options")
        cmd.extend(options)
    print("[geneval-select] running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
