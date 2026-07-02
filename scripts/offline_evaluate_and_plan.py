#!/usr/bin/env python3
"""Offline GenEval2 evaluation-to-retry planner for manual transfer packages."""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.offline_planner import EvalConfig, StopConfig, process_generation_package
from gen_retry.teachers.gpt55_teacher_adapter import GPT55TeacherAdapter
from gen_retry.teachers.mock_teacher import MockTeacher
from gen_retry.teachers.seed_teacher_adapter import SeedTeacherAdapter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consume Machine A generation packages, evaluate/normalize GenEval2, and emit retry actions."
    )
    parser.add_argument("--input", nargs="+", required=True, help="Generation package JSON path(s) or shell globs.")
    parser.add_argument("--output-dir", default="data/outgoing_retry_actions")
    parser.add_argument("--trajectory-dir", default="data/raw_trajectories")
    parser.add_argument("--resume-trajectory", help="Existing raw trajectory JSON. Use only with one --input.")
    parser.add_argument("--teacher", choices=["gpt55", "seed", "mock"], default="gpt55")
    parser.add_argument("--evaluator", choices=["geneval2"], default="geneval2")
    parser.add_argument("--geneval2-command-template", help="Optional command template when no eval result is present.")
    parser.add_argument("--geneval2-result", help="Optional raw or normalized GenEval2 result path for one input.")
    parser.add_argument("--benchmark-data", help="Optional GenEval2 benchmark JSONL for joining VQA/skill metadata.")
    parser.add_argument("--aggregate-by", default="prompt_id")
    parser.add_argument("--atom-threshold", type=float, default=0.5)
    parser.add_argument("--max-retry", type=int, default=3)
    parser.add_argument("--pass-threshold", type=float, default=0.95)
    parser.add_argument("--no-improvement-patience", type=int, default=1)
    parser.add_argument("--large-regression-score-delta", type=float, default=-0.15)
    parser.add_argument("--allow-retry-after-regression", action="store_true")
    args = parser.parse_args()

    inputs = _expand_inputs(args.input)
    if not inputs:
        raise ValueError("no input packages matched")
    if args.resume_trajectory and len(inputs) != 1:
        raise ValueError("--resume-trajectory can only be used with exactly one input")
    if args.geneval2_result and len(inputs) != 1:
        raise ValueError("--geneval2-result can only be used with exactly one input")

    teacher = _teacher(args.teacher)
    stop_config = StopConfig(
        max_retry=args.max_retry,
        pass_threshold=args.pass_threshold,
        no_improvement_patience=args.no_improvement_patience,
        large_regression_score_delta=args.large_regression_score_delta,
        allow_retry_after_regression=args.allow_retry_after_regression,
    )
    eval_config = EvalConfig(
        evaluator=args.evaluator,
        geneval2_command_template=args.geneval2_command_template,
        benchmark_data_path=args.benchmark_data,
        aggregate_by=args.aggregate_by,
        atom_threshold=args.atom_threshold,
        eval_result_path=args.geneval2_result,
    )

    failures = 0
    for package_path in inputs:
        try:
            result = process_generation_package(
                package_path,
                output_dir=args.output_dir,
                trajectory_dir=args.trajectory_dir,
                teacher=teacher,
                stop_config=stop_config,
                eval_config=eval_config,
                resume_trajectory=args.resume_trajectory,
            )
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ERROR {package_path}: {exc}", file=sys.stderr)
            continue
        output = result["output_package"]
        stop = output.get("stop", {})
        print(
            f"{package_path} -> {result['output_path']} "
            f"(trajectory={result['trajectory_path']}, stop={stop.get('should_stop')}:{stop.get('reason')})"
        )
    return 1 if failures else 0


def _expand_inputs(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        if matches:
            paths.extend(Path(item) for item in matches)
        else:
            paths.append(Path(pattern))
    return paths


def _teacher(name: str):
    if name == "mock":
        return MockTeacher()
    if name == "seed":
        return SeedTeacherAdapter()
    return GPT55TeacherAdapter()


if __name__ == "__main__":
    raise SystemExit(main())
