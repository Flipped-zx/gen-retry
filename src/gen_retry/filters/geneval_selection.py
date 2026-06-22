"""Selection helpers for GenEval prompt-level retry data mining."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


CandidatePolicy = str


def build_prompt_selection_rows(
    candidates: list[dict[str, Any]],
    *,
    min_score: float,
    max_score: float,
) -> list[dict[str, Any]]:
    """Aggregate per-image candidate scores into prompt-level score rows."""

    rows: list[dict[str, Any]] = []
    for sample_id, group in grouped_by_sample(candidates).items():
        scores = [candidate_score(item) for item in group]
        total = len(scores)
        score = sum(scores) / total if total else 0.0
        selected = min_score <= score <= max_score
        first = group[0] if group else {}
        rows.append(
            {
                "sample_id": sample_id,
                "prompt": first.get("prompt", ""),
                "category": first.get("category", ""),
                "prompt_score": score,
                "correct_count": sum(1 for value in scores if value >= 1.0),
                "total_count": total,
                "selected": selected,
                "candidate_ids": [str(item.get("candidate_id") or item.get("id")) for item in group],
            }
        )
    return sorted(rows, key=lambda item: str(item["sample_id"]))


def select_teacher_candidates(
    candidates: list[dict[str, Any]],
    *,
    min_score: float,
    max_score: float,
    candidate_policy: CandidatePolicy = "failed",
    max_rows: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return selected candidate rows and prompt-level selection metadata."""

    prompt_rows = build_prompt_selection_rows(candidates, min_score=min_score, max_score=max_score)
    selected_sample_ids = {str(row["sample_id"]) for row in prompt_rows if row.get("selected") is True}
    selected: list[dict[str, Any]] = []
    for sample_id, group in grouped_by_sample(candidates).items():
        if sample_id not in selected_sample_ids:
            continue
        prompt_row = next(row for row in prompt_rows if str(row["sample_id"]) == sample_id)
        chosen = choose_candidates(group, candidate_policy)
        for item in chosen:
            enriched = dict(item)
            enriched["selection_metadata"] = {
                "prompt_score": prompt_row["prompt_score"],
                "correct_count": prompt_row["correct_count"],
                "total_count": prompt_row["total_count"],
                "candidate_policy": candidate_policy,
                "min_prompt_score": min_score,
                "max_prompt_score": max_score,
            }
            selected.append(enriched)
            if max_rows is not None and len(selected) >= max_rows:
                return selected, prompt_rows
    return selected, prompt_rows


def choose_candidates(
    group: list[dict[str, Any]],
    candidate_policy: CandidatePolicy,
) -> list[dict[str, Any]]:
    """Choose candidate images from one selected prompt group."""

    policy = candidate_policy.strip().lower()
    if policy == "all":
        return list(group)
    failed = [item for item in group if is_failed_candidate(item)]
    if policy == "failed":
        return failed
    if policy == "best_failed":
        return _one_by_score(failed, reverse=True)
    if policy == "worst_failed":
        return _one_by_score(failed, reverse=False)
    raise ValueError(
        "candidate_policy must be one of: all, failed, best_failed, worst_failed"
    )


def grouped_by_sample(candidates: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        sample_id = str(item.get("sample_id") or item.get("id") or "unknown")
        grouped[sample_id].append(item)
    return dict(sorted(grouped.items(), key=lambda pair: pair[0]))


def candidate_score(candidate: dict[str, Any]) -> float:
    report = candidate.get("geneval_report") if isinstance(candidate.get("geneval_report"), dict) else {}
    try:
        return max(0.0, min(1.0, float(report.get("score", 0.0))))
    except (TypeError, ValueError):
        return 0.0


def is_failed_candidate(candidate: dict[str, Any]) -> bool:
    if candidate_score(candidate) < 1.0:
        return True
    diagnostic = candidate.get("diagnostic") if isinstance(candidate.get("diagnostic"), dict) else {}
    failed = diagnostic.get("failed_constraints")
    return isinstance(failed, list) and bool(failed)


def teacher_rows_from_selected(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract teacher rows and preserve selection metadata."""

    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        row = candidate.get("teacher_row")
        if not isinstance(row, dict):
            continue
        out = dict(row)
        if "selection_metadata" in candidate:
            out["selection_metadata"] = candidate["selection_metadata"]
        if "geneval_report" in candidate:
            out["geneval_report"] = candidate["geneval_report"]
        rows.append(out)
    return rows


def _one_by_score(group: list[dict[str, Any]], *, reverse: bool) -> list[dict[str, Any]]:
    if not group:
        return []
    return [sorted(group, key=candidate_score, reverse=reverse)[0]]
