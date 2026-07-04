#!/usr/bin/env python3
"""Snapshot completed sharded GenEval2 checkpoints for incremental retry planning."""

from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.evaluators.geneval2_result_normalizer import normalize_geneval2_score_list  # noqa: E402
from gen_retry.offline_planner import is_passed  # noqa: E402
from gen_retry.schemas.reports import NormalizedEvalReport  # noqa: E402
from gen_retry.utils.io import read_json, read_jsonl, write_json, write_jsonl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read raw_score_lists.json checkpoints from running GenEval2 shards, "
            "normalize completed candidates, and write per-worker snapshot inputs "
            "for concurrent teacher retry_replan calls."
        )
    )
    parser.add_argument("--manifest", required=True, help="Original generation_manifest.jsonl.")
    parser.add_argument("--shard-dir", action="append", default=[], help="Shard output dir. Can be repeated.")
    parser.add_argument("--shard-glob", help="Glob for shard output dirs.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--atom-threshold", type=float, default=0.9)
    parser.add_argument("--max-candidates", type=int)
    parser.add_argument(
        "--exclude-trajectory-dir",
        action="append",
        default=[],
        help="Skip candidate_ids that already have raw trajectory JSON in this directory.",
    )
    parser.add_argument(
        "--exclude-output-dir",
        action="append",
        default=[],
        help="Skip candidate_ids that already have retry action packages in this directory.",
    )
    args = parser.parse_args()

    if args.num_workers <= 0:
        raise ValueError("--num-workers must be positive")

    shard_dirs = [Path(value) for value in args.shard_dir]
    if args.shard_glob:
        shard_dirs.extend(Path(value) for value in glob.glob(args.shard_glob))
    shard_dirs = sorted({path.resolve() for path in shard_dirs})
    if not shard_dirs:
        raise ValueError("provide at least one --shard-dir or --shard-glob")

    manifest_rows = read_jsonl(args.manifest)
    manifest_by_candidate = {
        str(row.get("candidate_id", "")).strip(): row
        for row in manifest_rows
        if str(row.get("candidate_id", "")).strip()
    }
    exclude_ids = _existing_candidate_ids(args.exclude_trajectory_dir, args.exclude_output_dir)

    completed_jobs: list[dict[str, Any]] = []
    score_lists_by_candidate: dict[str, Any] = {}
    shard_progress: list[dict[str, Any]] = []
    issues: list[str] = []

    for shard_dir in shard_dirs:
        jobs_path = shard_dir / "diagnostic_jobs.jsonl"
        scores_path = shard_dir / "raw_score_lists.json"
        if not jobs_path.exists() or not scores_path.exists():
            issues.append(f"missing checkpoint files in {shard_dir}")
            continue
        jobs = read_jsonl(jobs_path)
        try:
            raw_scores = json.loads(scores_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(f"cannot read in-progress scores from {scores_path}: {exc}")
            raw_scores = []
        if not isinstance(raw_scores, list):
            issues.append(f"{scores_path} is not a JSON list")
            raw_scores = []
        done = min(len(jobs), len(raw_scores))
        shard_progress.append(
            {
                "shard_dir": str(shard_dir),
                "planned_jobs": len(jobs),
                "completed_score_lists": len(raw_scores),
                "usable_completed_jobs": done,
            }
        )
        for job, scores in zip(jobs[:done], raw_scores[:done], strict=True):
            candidate_id = str(job.get("candidate_id", "")).strip()
            if not candidate_id or candidate_id in exclude_ids:
                continue
            if candidate_id not in manifest_by_candidate:
                issues.append(f"completed candidate missing from manifest: {candidate_id}")
                continue
            completed_jobs.append(job)
            score_lists_by_candidate[candidate_id] = scores

    completed_jobs = _dedupe_jobs(completed_jobs)
    completed_jobs.sort(key=lambda row: str(row.get("candidate_id", "")))
    if args.max_candidates is not None:
        completed_jobs = completed_jobs[: args.max_candidates]
    completed_ids = {str(row.get("candidate_id", "")).strip() for row in completed_jobs}
    score_lists_by_candidate = {
        candidate_id: scores
        for candidate_id, scores in score_lists_by_candidate.items()
        if candidate_id in completed_ids
    }

    atom_rows = _atom_rows(completed_jobs, score_lists_by_candidate)
    reports = normalize_geneval2_score_list(
        atom_rows,
        aggregate_by="candidate_id",
        atom_threshold=args.atom_threshold,
    )
    report_rows = _report_rows(completed_jobs, reports, raw_eval_path=Path(args.output_dir) / "raw_score_lists.by_candidate.json")
    manifest_subset = [manifest_by_candidate[str(job["candidate_id"])] for job in completed_jobs]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "manifest.jsonl", manifest_subset)
    write_jsonl(output_dir / "diagnostic_jobs.jsonl", completed_jobs)
    write_jsonl(output_dir / "atom_rows.jsonl", atom_rows)
    write_jsonl(output_dir / "normalized_reports.jsonl", report_rows)
    write_json(output_dir / "raw_score_lists.by_candidate.json", dict(sorted(score_lists_by_candidate.items())))

    worker_rows = _write_worker_inputs(
        output_dir=output_dir,
        manifest_rows=manifest_subset,
        jobs=completed_jobs,
        report_rows=report_rows,
        num_workers=args.num_workers,
    )

    report_objects = {
        row["candidate_id"]: NormalizedEvalReport.from_dict(dict(row["normalized_report"]))
        for row in report_rows
        if isinstance(row.get("normalized_report"), dict)
    }
    pass_count = sum(1 for report in report_objects.values() if is_passed(report))
    failure_types: Counter[str] = Counter()
    for report in report_objects.values():
        failure_types.update(report.critical_failure_types)

    summary = {
        "schema_version": "v1",
        "status": "ok" if not issues else "warning",
        "manifest": args.manifest,
        "output_dir": str(output_dir),
        "shards": shard_progress,
        "excluded_existing": len(exclude_ids),
        "completed_candidates": len(completed_jobs),
        "atom_rows": len(atom_rows),
        "normalized_reports": len(report_rows),
        "pass_count": pass_count,
        "retry_candidate_count": len(report_rows) - pass_count,
        "failure_type_counts": dict(sorted(failure_types.items())),
        "workers": worker_rows,
        "issues": issues[:50],
    }
    write_json(output_dir / "snapshot_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


def _existing_candidate_ids(trajectory_dirs: list[str], output_dirs: list[str]) -> set[str]:
    candidate_ids: set[str] = set()
    for value in trajectory_dirs:
        directory = Path(value)
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            try:
                payload = read_json(path)
            except Exception:  # noqa: BLE001
                continue
            candidate_id = str(payload.get("candidate_id", "")).strip()
            if candidate_id:
                candidate_ids.add(candidate_id)
    for value in output_dirs:
        directory = Path(value)
        if not directory.exists():
            continue
        for path in directory.glob("*_retry_action_package.json"):
            try:
                payload = read_json(path)
            except Exception:  # noqa: BLE001
                continue
            candidate_id = str(payload.get("candidate_id", "")).strip()
            if candidate_id:
                candidate_ids.add(candidate_id)
    return candidate_ids


def _dedupe_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for job in jobs:
        candidate_id = str(job.get("candidate_id", "")).strip()
        if not candidate_id or candidate_id in seen:
            continue
        seen.add(candidate_id)
        deduped.append(job)
    return deduped


def _atom_rows(jobs: list[dict[str, Any]], score_lists_by_candidate: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for job in jobs:
        candidate_id = str(job["candidate_id"])
        scores = score_lists_by_candidate[candidate_id]
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
                    "candidate_id": candidate_id,
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
    reports: dict[str, NormalizedEvalReport],
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


def _write_worker_inputs(
    *,
    output_dir: Path,
    manifest_rows: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    report_rows: list[dict[str, Any]],
    num_workers: int,
) -> list[dict[str, Any]]:
    manifest_by_id = {str(row.get("candidate_id", "")): row for row in manifest_rows}
    jobs_by_id = {str(row.get("candidate_id", "")): row for row in jobs}
    reports_by_id = {str(row.get("candidate_id", "")): row for row in report_rows}
    candidate_ids = sorted(set(manifest_by_id) & set(jobs_by_id) & set(reports_by_id))
    worker_summaries: list[dict[str, Any]] = []
    for worker_index in range(num_workers):
        worker_ids = [
            candidate_id
            for index, candidate_id in enumerate(candidate_ids)
            if index % num_workers == worker_index
        ]
        worker_dir = output_dir / "workers" / f"worker_{worker_index:02d}"
        worker_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(worker_dir / "manifest.jsonl", [manifest_by_id[candidate_id] for candidate_id in worker_ids])
        write_jsonl(worker_dir / "diagnostic_jobs.jsonl", [jobs_by_id[candidate_id] for candidate_id in worker_ids])
        write_jsonl(worker_dir / "normalized_reports.jsonl", [reports_by_id[candidate_id] for candidate_id in worker_ids])
        worker_summaries.append(
            {
                "worker_index": worker_index,
                "candidate_count": len(worker_ids),
                "manifest": str(worker_dir / "manifest.jsonl"),
                "diagnostic_jobs": str(worker_dir / "diagnostic_jobs.jsonl"),
                "normalized_reports": str(worker_dir / "normalized_reports.jsonl"),
            }
        )
    return worker_summaries


if __name__ == "__main__":
    raise SystemExit(main())
