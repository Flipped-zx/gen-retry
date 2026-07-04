"""Build offline generation packages from Qwen/GenEval2 manifests.

The package builder is the bridge between a generation machine and the local
teacher-retry planner. It keeps image bytes optional for teacher planning: image
paths are retained as artifacts, while normalized GenEval2 reports and planner
history are the authoritative teacher inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from gen_retry.evaluators.geneval2_result_normalizer import (
    load_geneval2_score_rows,
    normalize_geneval2_score_list,
)
from gen_retry.offline_planner import CONTRACT_SCHEMA_VERSION
from gen_retry.schemas.actions import InitialPlanAction
from gen_retry.schemas.reports import NormalizedEvalReport
from gen_retry.utils.io import read_jsonl, write_json, write_jsonl


@dataclass(frozen=True)
class PackageBuildSummary:
    package_count: int
    package_manifest_path: str
    missing_initial_plan_count: int
    missing_eval_report_count: int
    missing_image_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_count": self.package_count,
            "package_manifest_path": self.package_manifest_path,
            "missing_initial_plan_count": self.missing_initial_plan_count,
            "missing_eval_report_count": self.missing_eval_report_count,
            "missing_image_count": self.missing_image_count,
        }


def build_generation_packages_from_manifest(
    *,
    manifest_path: str | Path,
    output_dir: str | Path,
    initial_plan_dir: str | Path | None = None,
    eval_results_path: str | Path | None = None,
    benchmark_data_path: str | Path | None = None,
    aggregate_by: str = "candidate_id",
    atom_threshold: float = 0.5,
    candidate_index: int | None = 0,
    all_candidates: bool = False,
    limit: int | None = None,
    round_id: int = 0,
    generator_name: str = "qwen-image-2512",
    require_initial_plan: bool = False,
) -> PackageBuildSummary:
    rows = read_jsonl(manifest_path)
    selected = select_manifest_rows(
        rows,
        candidate_index=candidate_index,
        all_candidates=all_candidates,
        limit=limit,
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    eval_index = (
        load_eval_report_index(
            eval_results_path,
            benchmark_data_path=benchmark_data_path,
            aggregate_by=aggregate_by,
            atom_threshold=atom_threshold,
        )
        if eval_results_path
        else {}
    )

    manifest_rows: list[dict[str, Any]] = []
    missing_initial_plan = 0
    missing_eval_report = 0
    missing_image = 0
    for index, row in enumerate(selected):
        plan, plan_path, plan_error = load_initial_plan(
            row,
            initial_plan_dir=initial_plan_dir,
        )
        if not plan:
            missing_initial_plan += 1
            if require_initial_plan:
                raise ValueError(
                    f"missing initial plan for candidate={_candidate_id(row, index)}: {plan_error}"
                )
        report, eval_key = find_eval_report(eval_index, row)
        if eval_results_path and report is None:
            missing_eval_report += 1
        package = build_generation_package(
            row,
            source_index=index,
            initial_plan=plan,
            initial_plan_path=plan_path,
            eval_report=report,
            eval_lookup_key=eval_key,
            round_id=round_id,
            generator_name=generator_name,
        )
        image_path = str(package.get("generation", {}).get("image_path", ""))
        if image_path and not Path(image_path).exists():
            missing_image += 1
        package_path = output / _package_filename(package)
        write_json(package_path, package)
        manifest_rows.append(
            {
                "package_path": str(package_path),
                "trajectory_id": package["trajectory_id"],
                "prompt_id": package["prompt_id"],
                "candidate_id": package["candidate_id"],
                "round": package["round"],
                "image_path": image_path,
                "image_exists_local": bool(image_path and Path(image_path).exists()),
                "has_initial_plan": bool(plan),
                "initial_plan_path": plan_path,
                "initial_plan_error": plan_error,
                "has_eval_report": report is not None,
                "eval_lookup_key": eval_key,
            }
        )

    package_manifest_path = output / "package_manifest.jsonl"
    write_jsonl(package_manifest_path, manifest_rows)
    return PackageBuildSummary(
        package_count=len(manifest_rows),
        package_manifest_path=str(package_manifest_path),
        missing_initial_plan_count=missing_initial_plan,
        missing_eval_report_count=missing_eval_report,
        missing_image_count=missing_image,
    )


def select_manifest_rows(
    rows: list[dict[str, Any]],
    *,
    candidate_index: int | None = 0,
    all_candidates: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    if all_candidates:
        selected = list(rows)
    else:
        has_candidate_index = any("candidate_index" in row for row in rows)
        selected = []
        seen_prompts: set[str] = set()
        for index, row in enumerate(rows):
            prompt_id = _prompt_id(row, index)
            if has_candidate_index and candidate_index is not None:
                try:
                    if int(row.get("candidate_index", -1)) != int(candidate_index):
                        continue
                except (TypeError, ValueError):
                    continue
            elif prompt_id in seen_prompts:
                continue
            seen_prompts.add(prompt_id)
            selected.append(row)
    if limit is not None:
        return selected[:limit]
    return selected


def build_generation_package(
    row: dict[str, Any],
    *,
    source_index: int,
    initial_plan: dict[str, Any] | None,
    initial_plan_path: str,
    eval_report: NormalizedEvalReport | None,
    eval_lookup_key: str,
    round_id: int,
    generator_name: str,
) -> dict[str, Any]:
    metadata = _metadata(row)
    prompt_id = _prompt_id(row, source_index)
    candidate_id = _candidate_id(row, source_index)
    original_prompt = str(
        row.get("original_prompt")
        or metadata.get("original_prompt")
        or metadata.get("prompt")
        or row.get("prompt")
        or ""
    )
    generation_prompt = str(
        row.get("generation_prompt")
        or metadata.get("generation_prompt")
        or row.get("prompt")
        or original_prompt
    )
    generation = {
        "generator_name": str(row.get("generator_name") or generator_name),
        "prompt_used": generation_prompt,
        "seed": row.get("seed"),
        "image_id": str(row.get("image_id") or candidate_id),
        "image_path": str(row.get("image_path") or metadata.get("image_path") or ""),
        "generation_metadata": {
            "candidate_index": row.get("candidate_index"),
            "generation_prompt_source": row.get("generation_prompt_source")
            or metadata.get("generation_prompt_source"),
            "model_path": row.get("model_path") or metadata.get("model_path"),
            "manifest_prompt_index": row.get("prompt_index"),
            "sample_id": row.get("sample_id"),
            "initial_plan_path": initial_plan_path,
        },
    }
    source = {
        "dataset": "geneval2",
        "source": metadata.get("source", "geneval2"),
        "source_index": metadata.get("source_index", row.get("prompt_index", source_index)),
        "original_prompt": original_prompt,
        "prompt": metadata.get("prompt", original_prompt),
        "prompt_id": prompt_id,
        "skills": list(metadata.get("skills") or []),
        "skill_counts": dict(metadata.get("skill_counts") or {}),
        "atom_count": metadata.get("atom_count"),
        "vqa_list": list(metadata.get("vqa_list") or []),
        "sampling_bucket": metadata.get("sampling_bucket"),
        "sampling_tags": list(metadata.get("sampling_tags") or []),
    }
    package: dict[str, Any] = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "trajectory_id": prompt_id,
        "prompt_id": prompt_id,
        "candidate_id": candidate_id,
        "round": int(round_id),
        "source": source,
        "generation": generation,
        "previous_initial_plan": dict(initial_plan or {}),
        "previous_action": None if int(round_id) == 0 else {},
        "retry_history": [],
        "metadata": {
            "contract": "offline_manual_transfer_v1",
            "teacher_uses_image_bytes": False,
            "image_path_is_artifact_reference": True,
            "eval_lookup_key": eval_lookup_key,
        },
    }
    if eval_report is not None:
        evaluation = eval_report.to_dict()
        evaluation["raw_eval_path"] = _raw_eval_path_from_report(eval_report)
        package["evaluation"] = evaluation
    return package


def load_initial_plan(
    row: dict[str, Any],
    *,
    initial_plan_dir: str | Path | None = None,
) -> tuple[dict[str, Any] | None, str, str]:
    prompt_id = _prompt_id(row, 0)
    candidates: list[Path] = []
    if initial_plan_dir:
        candidates.append(Path(initial_plan_dir) / f"{prompt_id}.json")
    metadata = _metadata(row)
    for key in ("initial_plan_path",):
        value = metadata.get(key) or row.get(key)
        if value:
            candidates.append(Path(str(value)))

    last_error = ""
    for path in candidates:
        if not path.exists():
            last_error = f"not found: {path}"
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                last_error = f"{path} root is not an object"
                continue
            plan_data = data.get("initial_plan") if isinstance(data.get("initial_plan"), dict) else data
            plan = InitialPlanAction.from_dict(dict(plan_data))
            return plan.to_dict(), str(path), ""
        except Exception as exc:  # noqa: BLE001
            last_error = f"{path}: {exc}"
    return None, str(candidates[0]) if candidates else "", last_error or "no initial plan path"


def load_eval_report_index(
    path: str | Path,
    *,
    benchmark_data_path: str | Path | None = None,
    aggregate_by: str = "candidate_id",
    atom_threshold: float = 0.5,
) -> dict[str, NormalizedEvalReport]:
    normalized = _load_normalized_eval_rows(path)
    if normalized:
        return normalized
    rows = load_geneval2_score_rows(path, benchmark_data=benchmark_data_path)
    reports = normalize_geneval2_score_list(
        rows,
        aggregate_by=aggregate_by,
        atom_threshold=atom_threshold,
    )
    return {str(key): value for key, value in reports.items()}


def find_eval_report(
    eval_index: dict[str, NormalizedEvalReport],
    row: dict[str, Any],
) -> tuple[NormalizedEvalReport | None, str]:
    if not eval_index:
        return None, ""
    metadata = _metadata(row)
    candidates = [
        row.get("candidate_id"),
        row.get("image_id"),
        row.get("image_path"),
        Path(str(row.get("image_path", ""))).name,
        row.get("sample_id"),
        metadata.get("prompt_id"),
        row.get("prompt_id"),
        metadata.get("source_index"),
        row.get("prompt_index"),
        metadata.get("prompt"),
        row.get("original_prompt"),
    ]
    for candidate in candidates:
        if candidate not in (None, "") and str(candidate) in eval_index:
            return eval_index[str(candidate)], str(candidate)
    return None, ""


def _load_normalized_eval_rows(path: str | Path) -> dict[str, NormalizedEvalReport]:
    source = Path(path)
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    data: Any
    if source.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        data = json.loads(text)
        if isinstance(data, dict):
            if _looks_like_report_container(data):
                rows = [data]
            else:
                for key in ("rows", "data", "results", "reports"):
                    if isinstance(data.get(key), list):
                        rows = data[key]
                        break
                else:
                    rows = []
        elif isinstance(data, list) and all(isinstance(item, dict) for item in data):
            rows = data
        else:
            rows = []
    index: dict[str, NormalizedEvalReport] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        report_data = _report_data_from_row(row)
        if report_data is None:
            continue
        try:
            report = NormalizedEvalReport.from_dict(report_data)
        except Exception:  # noqa: BLE001
            continue
        for key in _eval_keys(row, report):
            index.setdefault(key, report)
    return index


def _report_data_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("normalized_report", "normalized_eval_report", "evaluation", "geneval_report"):
        value = row.get(key)
        if isinstance(value, dict) and _looks_like_normalized_report(value):
            return value
    if _looks_like_normalized_report(row):
        return row
    return None


def _eval_keys(row: dict[str, Any], report: NormalizedEvalReport) -> list[str]:
    keys: list[str] = []
    raw_report = report.raw_report if isinstance(report.raw_report, dict) else {}
    for value in (
        row.get("candidate_id"),
        row.get("sample_id"),
        row.get("prompt_id"),
        row.get("group_id"),
        row.get("image_id"),
        row.get("image_path"),
        raw_report.get("group_id"),
    ):
        _append_key(keys, value)
        if value:
            _append_key(keys, Path(str(value)).name)
    raw_rows = raw_report.get("rows") if isinstance(raw_report.get("rows"), list) else []
    if raw_rows and isinstance(raw_rows[0], dict):
        first = raw_rows[0]
        for key in ("candidate_id", "prompt_id", "sample_id", "image_id", "image_path", "prompt"):
            value = first.get(key)
            _append_key(keys, value)
            if value:
                _append_key(keys, Path(str(value)).name)
    return keys


def _append_key(keys: list[str], value: Any) -> None:
    if value in (None, ""):
        return
    text = str(value)
    if text not in keys:
        keys.append(text)


def _raw_eval_path_from_report(report: NormalizedEvalReport) -> str:
    raw = report.raw_report if isinstance(report.raw_report, dict) else {}
    value = raw.get("raw_eval_path") or raw.get("source_path")
    return str(value or "")


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _prompt_id(row: dict[str, Any], index: int) -> str:
    metadata = _metadata(row)
    value = (
        metadata.get("prompt_id")
        or row.get("prompt_id")
        or row.get("sample_id")
        or row.get("id")
    )
    if value:
        return _safe_name(str(value))
    prompt = str(metadata.get("prompt") or row.get("original_prompt") or row.get("prompt") or "")
    digest = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:10]
    return f"prompt_{index:05d}_{digest}"


def _candidate_id(row: dict[str, Any], index: int) -> str:
    value = row.get("candidate_id") or row.get("image_id")
    if value:
        return _safe_name(str(value))
    candidate = row.get("candidate_index", 0)
    return f"{_prompt_id(row, index)}_cand_{int(candidate):02d}"


def _package_filename(package: dict[str, Any]) -> str:
    name = (
        f"{package.get('trajectory_id', 'trajectory')}__{package.get('candidate_id', 'candidate')}"
        f"__round_{int(package.get('round', 0))}_generation_package"
    )
    return _safe_name(name) + ".json"


def _looks_like_report_container(data: dict[str, Any]) -> bool:
    return _report_data_from_row(data) is not None


def _looks_like_normalized_report(data: dict[str, Any]) -> bool:
    return "score" in data and (
        "failed_constraints" in data or "passed_constraints" in data or "uncertain_constraints" in data
    )


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("._") or "item"
