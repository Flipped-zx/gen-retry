"""Normalize official GenEval2 score-list outputs into retry reports."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from gen_retry.schemas.reports import NormalizedConstraint, NormalizedEvalReport


COLOR_WORDS = {
    "red",
    "blue",
    "green",
    "yellow",
    "black",
    "white",
    "brown",
    "gray",
    "grey",
    "orange",
    "purple",
    "pink",
    "cyan",
    "magenta",
    "gold",
    "silver",
}

GENEVAL2_CRITICAL_FAILURE_TYPES = {
    "missing_object",
    "extra_object",
    "forbidden_object_present",
    "count_mismatch",
    "color_mismatch",
    "attribute_mismatch",
    "spatial_mismatch",
    "relation_mismatch",
    "action_mismatch",
}


def normalize_geneval2_score_list(
    score_list: list[dict[str, Any]],
    aggregate_by: str = "prompt_id",
    atom_threshold: float = 0.5,
) -> dict[str, NormalizedEvalReport]:
    """Group atom-level GenEval2 rows and return one report per group."""

    atom_threshold = _clamp_threshold(atom_threshold)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for index, row in enumerate(score_list):
        if not isinstance(row, dict):
            row = {"score": row, "atom_index": index}
        group_id = _group_id(row, aggregate_by=aggregate_by, fallback_index=index)
        grouped.setdefault(group_id, []).append(row)

    reports: dict[str, NormalizedEvalReport] = {}
    for group_id, rows in grouped.items():
        passed: list[NormalizedConstraint] = []
        failed: list[NormalizedConstraint] = []
        uncertain: list[NormalizedConstraint] = []
        scores: list[float] = []
        for row_index, row in enumerate(rows):
            row = dict(row)
            row.setdefault("atom_index", row_index)
            constraint = normalize_geneval2_row(row, atom_threshold=atom_threshold)
            score = _extract_score(row)
            if score is not None:
                scores.append(score)
            if constraint.status == "passed":
                passed.append(constraint)
            elif constraint.status == "failed":
                failed.append(constraint)
            else:
                uncertain.append(constraint)
        reports[group_id] = NormalizedEvalReport(
            score=mean(scores) if scores else _score_from_constraints(passed, failed, uncertain),
            passed_constraints=passed,
            failed_constraints=failed,
            uncertain_constraints=uncertain,
            critical_failure_types=_critical_failure_types(failed),
            raw_report={
                "group_id": group_id,
                "rows": rows,
                "diagnostic_atom_threshold": atom_threshold,
                "threshold_note": (
                    "This atom threshold is for training-time diagnostic normalization only. "
                    "It is not a replacement for official GenEval2 benchmark scoring."
                ),
            },
        )
    return reports


def normalize_geneval2_row(row: dict[str, Any], *, atom_threshold: float = 0.5) -> NormalizedConstraint:
    """Normalize one GenEval2 atom/VQA row into a constraint."""

    atom_threshold = _clamp_threshold(atom_threshold)
    question = _first_present(row, "question", "vqa_question", "query")
    expected = _first_present(row, "answer", "gt_answer", "expected_answer", "expected")
    detected = _first_present(row, "prediction", "pred", "model_answer", "detected")
    skill = _skill(row)
    status = _status(row, atom_threshold=atom_threshold)
    failure_type = _failure_type(skill=skill, question=question, status=status)
    return NormalizedConstraint(
        type=failure_type,
        target=_target(row, question),
        expected=expected,
        detected=detected if detected != "" else _detected_from_score(row),
        status=status,
        details={
            "question": question,
            "skill": skill,
            "score": _extract_score(row),
            "prompt_id": _first_present(row, "prompt_id", "sample_id", "id"),
            "image_id": _first_present(row, "image_id", "image_path"),
            "atom_index": row.get("atom_index"),
            "diagnostic_atom_threshold": atom_threshold,
            "raw": dict(row),
        },
    )


def load_geneval2_score_rows(path: str | Path, *, benchmark_data: str | Path | None = None) -> list[dict[str, Any]]:
    """Read official GenEval2 output formats into atom-level rows.

    Supports:
    - JSON list of atom row dicts.
    - JSON list of score lists from official ``evaluation.py``. When benchmark
      data is supplied, VQA questions and skills are joined by row index.
    - JSONL atom rows.
    """

    source = Path(path)
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if source.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, dict):
        for key in ("rows", "data", "score_rows", "results"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list, JSONL rows, or object with rows/data/results")
    if all(isinstance(item, dict) for item in data):
        return [dict(item) for item in data]
    if all(isinstance(item, list) for item in data):
        return _rows_from_official_score_lists(data, benchmark_data=benchmark_data)
    raise ValueError(f"{path} has unsupported GenEval2 score format")


def _rows_from_official_score_lists(
    score_lists: list[list[Any]],
    *,
    benchmark_data: str | Path | None,
) -> list[dict[str, Any]]:
    benchmark_rows = _load_benchmark_rows(benchmark_data) if benchmark_data else []
    rows: list[dict[str, Any]] = []
    for prompt_index, atom_scores in enumerate(score_lists):
        bench = benchmark_rows[prompt_index] if prompt_index < len(benchmark_rows) else {}
        vqa_list = bench.get("vqa_list") if isinstance(bench, dict) else None
        skills = bench.get("skills") if isinstance(bench, dict) else None
        candidate_id = _benchmark_value(bench, "candidate_id")
        prompt_id = _benchmark_value(bench, "prompt_id") or str(prompt_index)
        eval_prompt = _benchmark_value(bench, "prompt")
        original_prompt = _benchmark_value(bench, "original_prompt") or eval_prompt
        for atom_index, score in enumerate(atom_scores):
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
                    "prompt_id": prompt_id,
                    "source_index": bench.get("source_index") if isinstance(bench, dict) else None,
                    "candidate_index": bench.get("candidate_index") if isinstance(bench, dict) else None,
                    "prompt": original_prompt,
                    "eval_prompt": eval_prompt,
                    "atom_count": bench.get("atom_count") if isinstance(bench, dict) else None,
                    "atom_index": atom_index,
                    "question": question,
                    "answer": answer,
                    "score": score,
                    "skill": skill,
                }
            )
    return rows


def _benchmark_value(bench: dict[str, Any], key: str) -> str:
    if not isinstance(bench, dict):
        return ""
    value = bench.get(key)
    return "" if value in (None, "") else str(value)


def _load_benchmark_rows(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    source = Path(path)
    rows: list[dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _group_id(row: dict[str, Any], *, aggregate_by: str, fallback_index: int) -> str:
    if aggregate_by:
        value = row.get(aggregate_by)
        if value not in (None, ""):
            return str(value)
    for key in ("prompt_id", "sample_id", "id", "image_id", "image_path", "prompt"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return str(fallback_index)


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return ""


def _skill(row: dict[str, Any]) -> str:
    value = _first_present(row, "skill", "skills", "category")
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value).strip().lower()


def _status(row: dict[str, Any], *, atom_threshold: float) -> str:
    score = _extract_score(row)
    if score is not None:
        return "passed" if score >= atom_threshold else "failed"
    correct = _first_present(row, "correct", "is_correct", "passed")
    if isinstance(correct, bool):
        return "passed" if correct else "failed"
    if isinstance(correct, (int, float)):
        return "passed" if float(correct) >= 0.5 else "failed"
    status = str(_first_present(row, "status", "result")).strip().lower()
    if status in {"pass", "passed", "correct", "ok", "true"}:
        return "passed"
    if status in {"fail", "failed", "incorrect", "false"}:
        return "failed"
    return "uncertain"


def _clamp_threshold(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _extract_score(row: dict[str, Any]) -> float | None:
    for key in ("score", "soft_score", "prob", "probability"):
        value = row.get(key)
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        if isinstance(value, str):
            try:
                return max(0.0, min(1.0, float(value)))
            except ValueError:
                continue
    return None


def _failure_type(*, skill: str, question: Any, status: str) -> str:
    question_text = str(question).lower()
    skill = skill.lower()
    if skill == "count":
        return "count_mismatch"
    if skill == "attribute":
        return "color_mismatch" if _has_color_word(question_text) else "attribute_mismatch"
    if skill == "color":
        return "color_mismatch"
    if skill == "position":
        return "spatial_mismatch"
    if skill == "verb":
        return "relation_mismatch"
    if skill == "object":
        if status == "failed" and _is_negative_object_question(question_text):
            return "extra_object"
        return "missing_object"
    return _infer_failure_type_from_question(question_text)


def _has_color_word(question: str) -> bool:
    words = {part.strip(" ?!.,;:()[]{}\"'").lower() for part in question.split()}
    return bool(words & COLOR_WORDS)


def _is_negative_object_question(question: str) -> bool:
    negative_markers = (
        " no ",
        "without",
        "not contain",
        "not include",
        "any extra",
        "forbidden",
        "absent",
    )
    padded = f" {question.lower()} "
    return any(marker in padded for marker in negative_markers)


def _infer_failure_type_from_question(question: str) -> str:
    if "how many" in question or "exactly" in question:
        return "count_mismatch"
    if _has_color_word(question):
        return "color_mismatch"
    if any(marker in question for marker in ("left of", "right of", "in front of", "behind", "under", "above", "below")):
        return "spatial_mismatch"
    if any(marker in question for marker in ("playing", "chasing", "jumping", "holding", "riding")):
        return "relation_mismatch"
    return "missing_object"


def _target(row: dict[str, Any], question: Any) -> str:
    for key in ("target", "object", "entity"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return str(question or "geneval2_atom")


def _detected_from_score(row: dict[str, Any]) -> str:
    score = _extract_score(row)
    if score is None:
        return ""
    return f"soft_score={score:.6g}"


def _score_from_constraints(
    passed: list[NormalizedConstraint],
    failed: list[NormalizedConstraint],
    uncertain: list[NormalizedConstraint],
) -> float:
    total = len(passed) + len(failed) + len(uncertain)
    if total == 0:
        return 0.0
    return len(passed) / total


def _critical_failure_types(failed: list[NormalizedConstraint]) -> list[str]:
    return sorted({item.type for item in failed if item.type in GENEVAL2_CRITICAL_FAILURE_TYPES})
