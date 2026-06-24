"""Deterministic mock Geneval/Geneval2 evaluator for dry runs and tests."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from gen_retry.evaluators.base import BaseImageEvaluator
from gen_retry.evaluators.normalizer import normalize_eval_report
from gen_retry.schemas.reports import NormalizedEvalReport


class MockGenevalEvaluator(BaseImageEvaluator):
    name = "mock_geneval"

    def __init__(self, prompt_records: list[dict[str, Any]] | None = None, evaluator_type: str = "geneval") -> None:
        self.evaluator_type = evaluator_type
        self._reports_by_prompt: dict[str, list[dict[str, Any]]] = {}
        self._calls: dict[str, int] = defaultdict(int)
        for record in prompt_records or []:
            prompt = str(record.get("prompt", "")).strip()
            reports = record.get("mock_reports")
            if prompt and isinstance(reports, list):
                self._reports_by_prompt[prompt] = [
                    item for item in reports if isinstance(item, dict)
                ]

    def evaluate(self, original_prompt: str, image_path: str) -> NormalizedEvalReport:
        _ = image_path
        index = self._calls[original_prompt]
        self._calls[original_prompt] += 1
        reports = self._reports_by_prompt.get(original_prompt)
        if reports:
            return normalize_eval_report(
                reports[min(index, len(reports) - 1)],
                evaluator_type=self.evaluator_type,
            )
        if index == 0:
            return normalize_eval_report(_fallback_failure(original_prompt), evaluator_type=self.evaluator_type)
        return normalize_eval_report({"score": 1.0, "passed_constraints": [], "failed_constraints": []})


def _fallback_failure(prompt: str) -> dict[str, Any]:
    failure_types = [
        "count_mismatch",
        "color_mismatch",
        "spatial_mismatch",
        "missing_object",
        "extra_object",
        "relation_mismatch",
    ]
    failure_type = failure_types[sum(ord(ch) for ch in prompt) % len(failure_types)]
    return {
        "score": 0.55,
        "passed_constraints": [],
        "failed_constraints": [
            {
                "type": failure_type,
                "target": _target_for_failure(failure_type),
                "expected": _expected_for_failure(failure_type),
                "detected": _detected_for_failure(failure_type),
                "status": "failed",
            }
        ],
        "uncertain_constraints": [],
    }


def _target_for_failure(failure_type: str) -> str:
    return {
        "count_mismatch": "object count",
        "color_mismatch": "object color",
        "spatial_mismatch": "spatial relation",
        "relation_mismatch": "object relation",
        "missing_object": "required object",
        "extra_object": "extra object",
    }.get(failure_type, "constraint")


def _expected_for_failure(failure_type: str) -> str:
    return {
        "count_mismatch": "exact requested count",
        "color_mismatch": "requested color binding",
        "spatial_mismatch": "requested relative layout",
        "relation_mismatch": "requested relation",
        "missing_object": "object visible",
        "extra_object": "no extra object",
    }.get(failure_type, "expected constraint")


def _detected_for_failure(failure_type: str) -> str:
    return {
        "count_mismatch": "wrong count",
        "color_mismatch": "wrong color",
        "spatial_mismatch": "wrong layout",
        "relation_mismatch": "wrong relation",
        "missing_object": "object missing",
        "extra_object": "extra object present",
    }.get(failure_type, "failed constraint")
