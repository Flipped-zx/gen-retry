"""Lightweight Git handoff helpers for the two-machine retry loop."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from gen_retry.offline_planner import CONTRACT_SCHEMA_VERSION, trajectory_file_path
from gen_retry.schemas.reports import NormalizedEvalReport
from gen_retry.utils.io import read_json, read_jsonl, write_json, write_jsonl


EXCHANGE_SCHEMA_VERSION = "exchange.v1"


def package_gpu_to_api_handoff(
    *,
    generation_manifest_path: str | Path,
    geneval2_dir: str | Path,
    output_dir: str | Path,
    expected_count: int | None = None,
    include_atom_rows: bool = False,
) -> dict[str, Any]:
    """Copy only the lightweight GPU outputs needed by the API machine."""

    manifest_source = Path(generation_manifest_path)
    geneval2_source = Path(geneval2_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    generation_rows = read_jsonl(manifest_source)
    normalized_reports = read_jsonl(geneval2_source / "normalized_reports.jsonl")
    diagnostic_jobs = _read_jsonl_if_exists(geneval2_source / "diagnostic_jobs.jsonl")

    issues: list[str] = []
    if expected_count is not None and len(generation_rows) != expected_count:
        issues.append(f"generation manifest rows {len(generation_rows)} != expected {expected_count}")
    if expected_count is not None and len(normalized_reports) != expected_count:
        issues.append(f"normalized report rows {len(normalized_reports)} != expected {expected_count}")

    missing_vqa = [
        str(row.get("candidate_id") or row.get("sample_id") or index)
        for index, row in enumerate(generation_rows)
        if not _metadata_vqa_list(row)
    ]
    if missing_vqa:
        issues.append(f"generation rows missing metadata.vqa_list: {missing_vqa[:10]}")

    manifest_ids = _candidate_ids(generation_rows)
    report_ids = _candidate_ids(normalized_reports)
    job_ids = _candidate_ids(diagnostic_jobs)
    missing_reports = sorted(manifest_ids - report_ids)
    extra_reports = sorted(report_ids - manifest_ids)
    if missing_reports:
        issues.append(f"missing normalized reports for generated candidates: {missing_reports[:10]}")
    if extra_reports:
        issues.append(f"normalized reports without generated candidates: {extra_reports[:10]}")
    if diagnostic_jobs:
        missing_jobs = sorted(manifest_ids - job_ids)
        extra_jobs = sorted(job_ids - manifest_ids)
        if missing_jobs:
            issues.append(f"missing diagnostic jobs for generated candidates: {missing_jobs[:10]}")
        if extra_jobs:
            issues.append(f"diagnostic jobs without generated candidates: {extra_jobs[:10]}")

    files = {
        "generation_manifest": "generation_manifest.jsonl",
        "normalized_reports": "normalized_reports.jsonl",
    }
    write_jsonl(output / files["generation_manifest"], generation_rows)
    write_jsonl(output / files["normalized_reports"], normalized_reports)
    if diagnostic_jobs:
        files["diagnostic_jobs"] = "diagnostic_jobs.jsonl"
        write_jsonl(output / files["diagnostic_jobs"], diagnostic_jobs)

    for name in ("merge_summary.json", "geneval2_batch_plan.json"):
        source = geneval2_source / name
        if source.exists():
            files[name.removesuffix(".json")] = name
            write_json(output / name, read_json(source))

    if include_atom_rows:
        atom_rows = _read_jsonl_if_exists(geneval2_source / "atom_rows.jsonl")
        if atom_rows:
            files["atom_rows"] = "atom_rows.jsonl"
            write_jsonl(output / files["atom_rows"], atom_rows)

    summary = {
        "schema_version": EXCHANGE_SCHEMA_VERSION,
        "handoff_type": "gpu_to_api_geneval2",
        "status": "ok" if not issues else "error",
        "generation_manifest_source": str(manifest_source),
        "geneval2_dir_source": str(geneval2_source),
        "output_dir": str(output),
        "expected_count": expected_count,
        "counts": {
            "generation_manifest": len(generation_rows),
            "normalized_reports": len(normalized_reports),
            "diagnostic_jobs": len(diagnostic_jobs),
            "unique_generated_candidates": len(manifest_ids),
            "unique_report_candidates": len(report_ids),
            "unique_diagnostic_job_candidates": len(job_ids),
        },
        "files": files,
        "issues": issues,
    }
    write_json(output / "handoff_manifest.json", summary)
    return summary


def build_retry_continuation_packages(
    *,
    gpu_handoff_dir: str | Path,
    output_dir: str | Path,
    round_id: int | None = None,
    trajectory_dir: str | Path | None = None,
    generator_name: str = "qwen-image-2512",
    limit: int | None = None,
) -> dict[str, Any]:
    """Build API-side generation packages from a GPU GenEval2 handoff."""

    handoff = Path(gpu_handoff_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    generation_rows = read_jsonl(handoff / "generation_manifest.jsonl")
    if limit is not None:
        generation_rows = generation_rows[:limit]
    report_index = _report_index(read_jsonl(handoff / "normalized_reports.jsonl"))

    manifest_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index, row in enumerate(generation_rows):
        generated_candidate_id = str(row.get("candidate_id") or row.get("image_id") or "")
        try:
            if not generated_candidate_id:
                raise ValueError("generation row missing candidate_id")
            report, eval_lookup_key = _find_report(report_index, row)
            if report is None:
                raise ValueError(f"missing normalized report for {generated_candidate_id}")
            metadata = _metadata(row)
            current_round = _current_round(row, metadata, round_id=round_id)
            trajectory_path = _source_trajectory_path(metadata, trajectory_dir=trajectory_dir)
            if trajectory_path is None or not trajectory_path.exists():
                raise FileNotFoundError(
                    f"source trajectory not found for {generated_candidate_id}: "
                    f"{metadata.get('source_trajectory_path') or ''}"
                )
            trajectory = read_json(trajectory_path)
            previous_action = _previous_action_for_generation(metadata, trajectory)
            if not previous_action:
                raise ValueError(f"missing previous retry action for {generated_candidate_id}")

            package = _continuation_package(
                row,
                report=report,
                eval_lookup_key=eval_lookup_key,
                trajectory=trajectory,
                trajectory_path=trajectory_path,
                previous_action=previous_action,
                current_round=current_round,
                generated_candidate_id=generated_candidate_id,
                generator_name=generator_name,
                handoff_dir=handoff,
            )
            package_path = output / _package_filename(package)
            write_json(package_path, package)
            manifest_rows.append(
                {
                    "package_path": str(package_path),
                    "trajectory_id": package["trajectory_id"],
                    "prompt_id": package["prompt_id"],
                    "candidate_id": package["candidate_id"],
                    "generated_candidate_id": generated_candidate_id,
                    "round": package["round"],
                    "image_path": package["generation"]["image_path"],
                    "source_trajectory_path": str(trajectory_path),
                    "has_eval_report": True,
                    "eval_lookup_key": eval_lookup_key,
                }
            )
        except Exception as exc:  # noqa: BLE001 - failures are handoff data.
            failures.append(
                {
                    "row_index": index,
                    "candidate_id": generated_candidate_id,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                }
            )

    package_manifest_path = output / "package_manifest.jsonl"
    write_jsonl(package_manifest_path, manifest_rows)
    write_jsonl(output / "package_failures.jsonl", failures)
    summary = {
        "schema_version": EXCHANGE_SCHEMA_VERSION,
        "handoff_type": "api_retry_continuation_packages",
        "status": "ok" if not failures and manifest_rows else "error",
        "gpu_handoff_dir": str(handoff),
        "output_dir": str(output),
        "round": round_id,
        "packages_written": len(manifest_rows),
        "failures": len(failures),
        "package_manifest_path": str(package_manifest_path),
        "package_failures_path": str(output / "package_failures.jsonl"),
    }
    write_json(output / "package_summary.json", summary)
    return summary


def _continuation_package(
    row: dict[str, Any],
    *,
    report: dict[str, Any],
    eval_lookup_key: str,
    trajectory: dict[str, Any],
    trajectory_path: Path,
    previous_action: dict[str, Any],
    current_round: int,
    generated_candidate_id: str,
    generator_name: str,
    handoff_dir: Path,
) -> dict[str, Any]:
    metadata = _metadata(row)
    source = _source_payload(trajectory, metadata)
    prompt_id = str(trajectory.get("prompt_id") or metadata.get("original_prompt_id") or source.get("prompt_id") or "")
    candidate_id = str(
        trajectory.get("candidate_id")
        or metadata.get("original_candidate_id")
        or metadata.get("candidate_id")
        or ""
    )
    trajectory_id = str(trajectory.get("trajectory_id") or prompt_id)
    generation_prompt = str(row.get("generation_prompt") or row.get("prompt") or "")
    if not generation_prompt:
        raise ValueError(f"{generated_candidate_id} missing generation prompt")
    package = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "trajectory_id": trajectory_id,
        "prompt_id": prompt_id,
        "candidate_id": candidate_id,
        "round": current_round,
        "source": source,
        "generation": {
            "generator_name": str(row.get("generator_name") or generator_name),
            "prompt_used": generation_prompt,
            "seed": row.get("seed"),
            "image_id": generated_candidate_id,
            "image_path": str(row.get("image_path") or ""),
            "generation_metadata": {
                "candidate_index": row.get("candidate_index"),
                "prompt_index": row.get("prompt_index"),
                "sample_id": row.get("sample_id"),
                "generated_candidate_id": generated_candidate_id,
                "generation_prompt_source": row.get("generation_prompt_source")
                or metadata.get("generation_prompt_source"),
                "source_trajectory_path": str(trajectory_path),
                "gpu_handoff_dir": str(handoff_dir),
            },
        },
        "evaluation": report,
        "previous_initial_plan": dict(trajectory.get("initial_plan") or {}),
        "previous_action": previous_action,
        "retry_history": [],
        "metadata": {
            "contract": "offline_manual_transfer_v1",
            "exchange_schema_version": EXCHANGE_SCHEMA_VERSION,
            "teacher_uses_image_bytes": False,
            "image_path_is_artifact_reference": True,
            "eval_lookup_key": eval_lookup_key,
            "generated_candidate_id": generated_candidate_id,
            "source_trajectory_path": str(trajectory_path),
            "gpu_handoff_dir": str(handoff_dir),
        },
    }
    return package


def _source_payload(trajectory: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    source = dict(trajectory.get("source") or {})
    original_prompt = str(
        source.get("original_prompt")
        or metadata.get("prompt")
        or metadata.get("original_prompt")
        or ""
    )
    source.setdefault("dataset", metadata.get("dataset", "geneval2"))
    source.setdefault("source", metadata.get("source", "geneval2"))
    source.setdefault("source_index", metadata.get("source_index"))
    source.setdefault("prompt_id", metadata.get("original_prompt_id") or metadata.get("prompt_id"))
    source.setdefault("prompt", original_prompt)
    source["original_prompt"] = original_prompt
    if not source.get("skills"):
        source["skills"] = list(metadata.get("skills") or [])
    if not source.get("skill_counts"):
        source["skill_counts"] = dict(metadata.get("skill_counts") or {})
    if not source.get("vqa_list"):
        source["vqa_list"] = list(metadata.get("vqa_list") or [])
    source.setdefault("atom_count", metadata.get("atom_count"))
    source.setdefault("sampling_bucket", metadata.get("sampling_bucket"))
    source.setdefault("sampling_tags", list(metadata.get("sampling_tags") or []))
    return source


def _report_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        report = _report_payload(row)
        for key in _report_keys(row, report):
            index.setdefault(key, report)
    return index


def _find_report(index: dict[str, dict[str, Any]], row: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    metadata = _metadata(row)
    candidates = [
        row.get("candidate_id"),
        row.get("image_id"),
        row.get("image_path"),
        Path(str(row.get("image_path", ""))).name,
        row.get("sample_id"),
        row.get("prompt_id"),
        metadata.get("prompt_id"),
    ]
    for candidate in candidates:
        if candidate not in (None, "") and str(candidate) in index:
            return dict(index[str(candidate)]), str(candidate)
    return None, ""


def _report_payload(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    for key in ("normalized_report", "normalized_eval_report", "evaluation", "geneval_report"):
        value = row.get(key)
        if isinstance(value, dict) and _looks_like_normalized_report(value):
            data = dict(value)
            break
    if not _looks_like_normalized_report(data):
        raise ValueError("normalized report row missing score/constraints")
    report = NormalizedEvalReport.from_dict(data).to_dict()
    raw_eval_path = data.get("raw_eval_path") or row.get("raw_eval_path")
    if raw_eval_path:
        report["raw_eval_path"] = str(raw_eval_path)
    else:
        report["raw_eval_path"] = "normalized_reports.jsonl"
    return report


def _report_keys(row: dict[str, Any], report: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    raw_report = report.get("raw_report") if isinstance(report.get("raw_report"), dict) else {}
    for value in (
        row.get("candidate_id"),
        row.get("sample_id"),
        row.get("prompt_id"),
        row.get("group_id"),
        row.get("image_id"),
        row.get("image_path"),
        raw_report.get("group_id") if isinstance(raw_report, dict) else None,
    ):
        _append_key(keys, value)
        if value:
            _append_key(keys, Path(str(value)).name)
    return keys


def _source_trajectory_path(metadata: dict[str, Any], *, trajectory_dir: str | Path | None) -> Path | None:
    raw_path = metadata.get("source_trajectory_path")
    if raw_path:
        path = Path(str(raw_path))
        if path.exists():
            return path
        cwd_path = Path.cwd() / path
        if cwd_path.exists():
            return cwd_path
    if trajectory_dir:
        original_prompt_id = str(metadata.get("original_prompt_id") or metadata.get("prompt_id") or "")
        original_candidate_id = str(metadata.get("original_candidate_id") or "")
        if original_prompt_id and original_candidate_id:
            fallback = trajectory_file_path(
                {"trajectory_id": original_prompt_id, "candidate_id": original_candidate_id},
                trajectory_dir=trajectory_dir,
            )
            if fallback.exists():
                return fallback
    return Path(str(raw_path)) if raw_path else None


def _previous_action_for_generation(metadata: dict[str, Any], trajectory: dict[str, Any]) -> dict[str, Any]:
    for value in (
        metadata.get("previous_action"),
        trajectory.get("retry_ready_action"),
        trajectory.get("latest_teacher_action"),
    ):
        if isinstance(value, dict) and value.get("action_type") == "retry_replan":
            return dict(value)
    return {}


def _current_round(row: dict[str, Any], metadata: dict[str, Any], *, round_id: int | None) -> int:
    value = round_id
    if value is None:
        value = metadata.get("retry_round") or row.get("retry_round")
    if value is None:
        raise ValueError("round is required; pass --round or include metadata.retry_round")
    return int(value)


def _candidate_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("candidate_id")) for row in rows if row.get("candidate_id") not in (None, "")}


def _metadata_vqa_list(row: dict[str, Any]) -> list[Any]:
    metadata = _metadata(row)
    value = metadata.get("vqa_list")
    return list(value) if isinstance(value, list) else []


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        return dict(metadata)
    return {}


def _read_jsonl_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return read_jsonl(path)


def _looks_like_normalized_report(data: dict[str, Any]) -> bool:
    return "score" in data and (
        "failed_constraints" in data or "passed_constraints" in data or "uncertain_constraints" in data
    )


def _package_filename(package: dict[str, Any]) -> str:
    name = (
        f"{package.get('trajectory_id', 'trajectory')}__{package.get('candidate_id', 'candidate')}"
        f"__round_{int(package.get('round', 0)):02d}_generation_package"
    )
    return _safe_name(name) + ".json"


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("._") or "item"


def _append_key(keys: list[str], value: Any) -> None:
    if value in (None, ""):
        return
    text = str(value)
    if text not in keys:
        keys.append(text)
