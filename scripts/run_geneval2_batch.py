#!/usr/bin/env python3
"""Run GenEval2 over a batch of Qwen candidate images."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.evaluators.geneval2_result_normalizer import (  # noqa: E402
    normalize_geneval2_score_list,
)
from gen_retry.utils.io import read_jsonl, write_json, write_jsonl  # noqa: E402


DEFAULT_QWEN3VL_MODEL_PATH = "/root/private_data/agentic_image/models/Qwen3-VL-8B-Instruct"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Qwen candidates with GenEval2 in batch.")
    parser.add_argument("--metadata", help="Prompt JSONL used for image generation.")
    parser.add_argument("--image-dir", help="Qwen image output dir in official GenEval layout.")
    parser.add_argument("--manifest", help="Optional generation_manifest.jsonl.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--geneval2-root", default="../GenEval2")
    parser.add_argument("--method", default="soft_tifa_gm", choices=["tifa", "soft_tifa_am", "soft_tifa_gm"])
    parser.add_argument("--qwen3vl-model-path", default=DEFAULT_QWEN3VL_MODEL_PATH)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--work-dir",
        help=(
            "Directory for temporary patched GenEval2 scripts and inputs. "
            "Defaults to <output-dir>/.tmp so local runs do not write outside the repository."
        ),
    )
    parser.add_argument("--n-samples", type=int, default=5)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--candidate-index",
        type=int,
        help="When --manifest is used, evaluate only this candidate index per prompt.",
    )
    parser.add_argument("--num-shards", type=int, default=1, help="Split selected jobs into this many shards.")
    parser.add_argument("--shard-index", type=int, default=0, help="Run this zero-based shard index.")
    parser.add_argument("--atom-threshold", type=float, default=0.9)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--plan-only", action="store_true", help="Write batch inputs but do not run GenEval2.")
    parser.add_argument("--keep-eval-inputs", action="store_true")
    args = parser.parse_args()

    if not args.manifest and not (args.metadata and args.image_dir):
        raise ValueError("provide --manifest or both --metadata and --image-dir")
    if args.n_samples <= 0:
        raise ValueError("--n-samples must be positive")
    if args.num_shards <= 0:
        raise ValueError("--num-shards must be positive")
    if args.shard_index < 0 or args.shard_index >= args.num_shards:
        raise ValueError("--shard-index must be in [0, --num-shards)")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_scores_path = output_dir / "raw_score_lists.json"
    atom_rows_path = output_dir / "atom_rows.jsonl"
    reports_path = output_dir / "normalized_reports.jsonl"
    plan_path = output_dir / "geneval2_batch_plan.json"
    diagnostic_jobs_path = output_dir / "diagnostic_jobs.jsonl"
    missing_path = output_dir / "missing_images.jsonl"

    jobs, missing = _jobs(args)
    if args.num_shards > 1:
        jobs = _select_shard(jobs, num_shards=args.num_shards, shard_index=args.shard_index)
        missing = _select_shard(missing, num_shards=args.num_shards, shard_index=args.shard_index)
    write_jsonl(diagnostic_jobs_path, jobs)
    if missing:
        write_jsonl(missing_path, missing)
        if not args.allow_partial:
            raise FileNotFoundError(
                f"{len(missing)} image(s) are missing; see {missing_path}. "
                "Pass --allow-partial to evaluate existing images only."
            )
    if not jobs:
        raise ValueError("no evaluable image jobs found")

    write_json(plan_path, _plan_payload(args, jobs=jobs, missing=missing))
    print(
        f"planned GenEval2 jobs={len(jobs)} missing={len(missing)} output_dir={output_dir}",
        flush=True,
    )
    if args.plan_only:
        _write_eval_inputs(
            output_dir / "eval_benchmark.jsonl",
            output_dir / "eval_image_paths.json",
            jobs,
        )
        print("plan-only mode: GenEval2 was not run", flush=True)
        return 0
    completed_score_lists = _load_completed_score_lists(raw_scores_path) if args.resume else []
    if len(completed_score_lists) > len(jobs):
        raise ValueError(f"{raw_scores_path} has {len(completed_score_lists)} score lists for {len(jobs)} jobs")
    if args.resume and len(completed_score_lists) == len(jobs) and atom_rows_path.exists() and reports_path.exists():
        print(f"resume: existing outputs found in {output_dir}", flush=True)
        return 0
    run_jobs = jobs[len(completed_score_lists) :]
    if completed_score_lists:
        print(
            f"resume: found {len(completed_score_lists)} completed GenEval2 score list(s); "
            f"remaining={len(run_jobs)}",
            flush=True,
        )

    if run_jobs:
        work_root = Path(args.work_dir) if args.work_dir else output_dir / ".tmp"
        work_root.mkdir(parents=True, exist_ok=True)
        work_root = work_root.resolve()
        with TemporaryDirectory(prefix="geneval2_batch_", dir=work_root) as tmp:
            tmpdir = Path(tmp)
            eval_script = _prepare_evaluation_script(
                Path(args.geneval2_root),
                tmpdir,
                qwen3vl_model_path=args.qwen3vl_model_path,
            )
            benchmark_path = tmpdir / "benchmark.jsonl"
            image_map_path = tmpdir / "image_paths.json"
            if args.keep_eval_inputs and not completed_score_lists:
                benchmark_path = output_dir / "eval_benchmark.jsonl"
                image_map_path = output_dir / "eval_image_paths.json"
            _write_eval_inputs(benchmark_path, image_map_path, run_jobs)
            started = time.time()
            run_scores_path = raw_scores_path if not completed_score_lists else output_dir / "raw_score_lists.remaining.json"
            if completed_score_lists and run_scores_path.exists():
                run_scores_path.unlink()
            command = [
                args.python,
                str(eval_script),
                "--benchmark_data",
                str(benchmark_path.resolve()),
                "--image_filepath_data",
                str(image_map_path.resolve()),
                "--method",
                args.method,
                "--output_file",
                str(run_scores_path.resolve()),
            ]
            print(f"running GenEval2 jobs={len(run_jobs)} method={args.method}", flush=True)
            subprocess.run(command, cwd=str(Path(args.geneval2_root).resolve()), check=True)
            print(f"GenEval2 elapsed_seconds={time.time() - started:.1f}", flush=True)
            run_score_lists = _load_completed_score_lists(run_scores_path)
            if completed_score_lists:
                score_lists = completed_score_lists + run_score_lists
                raw_scores_path.write_text(
                    json.dumps(score_lists, ensure_ascii=False),
                    encoding="utf-8",
                )
                run_scores_path.unlink(missing_ok=True)
    else:
        score_lists = completed_score_lists

    score_lists = json.loads(raw_scores_path.read_text(encoding="utf-8"))
    if not isinstance(score_lists, list):
        raise ValueError(f"{raw_scores_path} must contain a JSON list")
    if len(score_lists) != len(jobs):
        raise ValueError(f"score list count {len(score_lists)} != job count {len(jobs)}")
    atom_rows = _atom_rows(jobs, score_lists)
    write_jsonl(atom_rows_path, atom_rows)
    reports = normalize_geneval2_score_list(
        atom_rows,
        aggregate_by="candidate_id",
        atom_threshold=args.atom_threshold,
    )
    report_rows = _report_rows(jobs, reports, raw_eval_path=raw_scores_path)
    write_jsonl(reports_path, report_rows)
    print(f"wrote atom rows -> {atom_rows_path}", flush=True)
    print(f"wrote normalized reports -> {reports_path}", flush=True)
    return 0


def _jobs(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if args.manifest:
        rows = read_jsonl(args.manifest)
        return _jobs_from_manifest(
            rows,
            limit=args.limit,
            n_samples=args.n_samples,
            candidate_index=args.candidate_index,
        )
    prompt_rows = read_jsonl(args.metadata)
    if args.limit is not None:
        prompt_rows = prompt_rows[: args.limit]
    return _jobs_from_image_layout(prompt_rows, Path(args.image_dir), args.n_samples)


def _jobs_from_manifest(
    rows: list[dict[str, Any]],
    *,
    limit: int | None = None,
    n_samples: int = 5,
    candidate_index: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    jobs: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    if candidate_index is None and limit is not None:
        rows = rows[: limit * n_samples]
    prompt_seen: set[str] = set()
    for index, row in enumerate(rows):
        metadata = dict(row.get("metadata") or {})
        row_candidate_index = int(row.get("candidate_index", 0))
        prompt_id = str(
            row.get("sample_id")
            or row.get("prompt_id")
            or metadata.get("prompt_id")
            or row.get("prompt_index", index)
        )
        if candidate_index is not None:
            if row_candidate_index != candidate_index:
                continue
            if limit is not None and prompt_id not in prompt_seen and len(prompt_seen) >= limit:
                continue
            prompt_seen.add(prompt_id)
        image_path = Path(str(row.get("image_path", "")))
        prompt = str(
            row.get("original_prompt")
            or metadata.get("original_prompt")
            or metadata.get("prompt")
            or row.get("prompt")
            or ""
        )
        job = {
            "candidate_id": str(row.get("candidate_id") or f"candidate_{index:06d}"),
            "prompt_id": prompt_id,
            "prompt": prompt,
            "source_index": metadata.get("source_index", row.get("source_index", row.get("prompt_index"))),
            "candidate_index": row_candidate_index,
            "image_path": str(image_path),
            "prompt_metadata": metadata or dict(row),
        }
        if image_path.exists():
            jobs.append(job)
        else:
            missing.append(job)
    return jobs, missing


def _jobs_from_image_layout(
    prompt_rows: list[dict[str, Any]],
    image_dir: Path,
    n_samples: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    jobs: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for prompt_index, row in enumerate(prompt_rows):
        prompt_id = str(row.get("prompt_id") or f"{prompt_index:05d}")
        prompt = str(row.get("prompt", "")).strip()
        for candidate_index in range(n_samples):
            candidate_id = f"{prompt_id}_cand_{candidate_index:02d}"
            image_path = image_dir / f"{prompt_index:05d}" / "samples" / f"{candidate_index:05d}.png"
            job = {
                "candidate_id": candidate_id,
                "prompt_id": prompt_id,
                "prompt": prompt,
                "source_index": row.get("source_index", prompt_index),
                "candidate_index": candidate_index,
                "image_path": str(image_path),
                "prompt_metadata": row,
            }
            if image_path.exists():
                jobs.append(job)
            else:
                missing.append(job)
    return jobs, missing


def _select_shard(rows: list[dict[str, Any]], *, num_shards: int, shard_index: int) -> list[dict[str, Any]]:
    if num_shards == 1:
        return rows
    return [row for index, row in enumerate(rows) if index % num_shards == shard_index]


def _write_eval_inputs(benchmark_path: Path, image_map_path: Path, jobs: list[dict[str, Any]]) -> None:
    benchmark_rows = []
    image_map: dict[str, str] = {}
    for job in jobs:
        metadata = dict(job.get("prompt_metadata") or {})
        eval_key = str(job["candidate_id"])
        benchmark_rows.append(
            {
                **metadata,
                "prompt": eval_key,
                "original_prompt": job["prompt"],
                "prompt_id": job["prompt_id"],
                "candidate_id": job["candidate_id"],
                "candidate_index": job["candidate_index"],
                "source_index": job["source_index"],
            }
        )
        image_map[eval_key] = str(Path(job["image_path"]).resolve())
    write_jsonl(benchmark_path, benchmark_rows)
    image_map_path.parent.mkdir(parents=True, exist_ok=True)
    image_map_path.write_text(json.dumps(image_map, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _prepare_evaluation_script(
    geneval2_root: Path,
    tmpdir: Path,
    *,
    qwen3vl_model_path: str,
) -> Path:
    source = geneval2_root / "evaluation.py"
    text = source.read_text(encoding="utf-8")
    for model_ref in (
        "Qwen/Qwen3-VL-8B-Instruct",
        "/root/private_data/agentic_image/models/Qwen3-VL-8B-Instruct",
    ):
        text = text.replace(model_ref, qwen3vl_model_path)
    text = text.replace(
        "torch_dtype='auto',\n                device_map='auto'",
        "torch_dtype='auto',\n                device_map='auto',\n                local_files_only=True",
    )
    text = text.replace(
        'dtype="auto", \n            device_map="auto"',
        'dtype="auto", \n            device_map="auto",\n            local_files_only=True',
    )
    text = text.replace(
        "        all_score_lists.append(score_list)\n",
        "        all_score_lists.append(score_list)\n"
        "        json.dump(all_score_lists, open(args.output_file, 'w'))\n",
    )
    target = tmpdir / "evaluation_local_qwen3vl.py"
    target.write_text(text, encoding="utf-8")
    return target


def _load_completed_score_lists(path: Path) -> list[Any]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list")
    return data


def _atom_rows(jobs: list[dict[str, Any]], score_lists: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for job, scores in zip(jobs, score_lists, strict=True):
        metadata = dict(job.get("prompt_metadata") or {})
        vqa_list = metadata.get("vqa_list", [])
        skills = metadata.get("skills", [])
        if not isinstance(scores, list):
            scores = [scores]
        for atom_index, score in enumerate(scores):
            question = ""
            answer = ""
            if isinstance(vqa_list, list) and atom_index < len(vqa_list):
                pair = vqa_list[atom_index]
                if isinstance(pair, list) and len(pair) >= 2:
                    question = str(pair[0])
                    answer = str(pair[1])
            skill = ""
            if isinstance(skills, list) and atom_index < len(skills):
                skill = str(skills[atom_index])
            rows.append(
                {
                    "candidate_id": job["candidate_id"],
                    "prompt_id": job["prompt_id"],
                    "source_index": job["source_index"],
                    "prompt": job["prompt"],
                    "candidate_index": job["candidate_index"],
                    "atom_count": metadata.get("atom_count"),
                    "atom_index": atom_index,
                    "question": question,
                    "answer": answer,
                    "score": score,
                    "skill": skill,
                    "image_id": job["image_path"],
                    "image_path": job["image_path"],
                }
            )
    return rows


def _report_rows(
    jobs: list[dict[str, Any]],
    reports: dict[str, Any],
    *,
    raw_eval_path: str | Path,
) -> list[dict[str, Any]]:
    job_by_id = {str(job["candidate_id"]): job for job in jobs}
    rows = []
    for candidate_id in sorted(reports):
        report = reports[candidate_id]
        job = job_by_id.get(candidate_id, {})
        normalized_report = report.to_dict()
        raw_report = dict(normalized_report.get("raw_report") or {})
        raw_report.setdefault("raw_eval_path", str(raw_eval_path))
        raw_report.setdefault("source_path", str(raw_eval_path))
        normalized_report["raw_report"] = raw_report
        rows.append(
            {
                "candidate_id": candidate_id,
                "prompt_id": job.get("prompt_id", ""),
                "prompt": job.get("prompt", ""),
                "source_index": job.get("source_index"),
                "candidate_index": job.get("candidate_index"),
                "image_path": job.get("image_path", ""),
                "raw_eval_path": str(raw_eval_path),
                "normalized_report": normalized_report,
            }
        )
    return rows


def _plan_payload(
    args: argparse.Namespace,
    *,
    jobs: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "created_at_unix": time.time(),
        "metadata": args.metadata,
        "image_dir": args.image_dir,
        "manifest": args.manifest,
        "geneval2_root": args.geneval2_root,
        "method": args.method,
        "qwen3vl_model_path": args.qwen3vl_model_path,
        "n_samples": args.n_samples,
        "limit": args.limit,
        "num_shards": args.num_shards,
        "shard_index": args.shard_index,
        "planned_jobs": len(jobs),
        "missing_images": len(missing),
        "first_jobs": jobs[:5],
    }


if __name__ == "__main__":
    raise SystemExit(main())
