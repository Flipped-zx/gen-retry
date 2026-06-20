"""Deterministic mock Geneval evaluator."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from gen_retry.evaluators.base import BaseEvaluator
from gen_retry.evaluators.geneval_normalizer import normalize_geneval_report, report_from_failure
from gen_retry.schemas.episode_schema import NormalizedGenevalReport


class MockGenevalEvaluator(BaseEvaluator):
    """Return deterministic reports from prompt metadata or a stable fallback."""

    def __init__(self, prompt_records: list[dict[str, Any]] | None = None) -> None:
        self._reports_by_prompt: dict[str, list[dict[str, Any]]] = {}
        self._calls: dict[str, int] = defaultdict(int)
        for record in prompt_records or []:
            prompt = str(record.get("prompt", "")).strip()
            reports = record.get("mock_reports")
            if prompt and isinstance(reports, list):
                self._reports_by_prompt[prompt] = [
                    item for item in reports if isinstance(item, dict)
                ]

    def evaluate(self, original_prompt: str, image_path: str) -> NormalizedGenevalReport:
        _ = image_path
        call_index = self._calls[original_prompt]
        self._calls[original_prompt] += 1
        reports = self._reports_by_prompt.get(original_prompt)
        if reports:
            raw = reports[min(call_index, len(reports) - 1)]
            return normalize_geneval_report(raw)
        return self._fallback_report(original_prompt, call_index)

    def _fallback_report(self, prompt: str, call_index: int) -> NormalizedGenevalReport:
        if call_index > 0:
            return report_from_failure(
                failure_type=None,
                target="prompt",
                expected="all constraints",
                detected="all constraints",
                score=1.0,
            )
        failure_types = [
            "count_mismatch",
            "color_mismatch",
            "spatial_mismatch",
            "missing_object",
            "extra_object",
        ]
        failure_type = failure_types[sum(ord(ch) for ch in prompt) % len(failure_types)]
        return report_from_failure(
            failure_type=failure_type,
            target=_target_for_failure(failure_type),
            expected=_expected_for_failure(failure_type),
            detected=_detected_for_failure(failure_type),
            score=0.55,
        )


def _target_for_failure(failure_type: str) -> str:
    return {
        "count_mismatch": "object count",
        "color_mismatch": "object color",
        "spatial_mismatch": "spatial relation",
        "missing_object": "required object",
        "extra_object": "extra object",
    }.get(failure_type, "constraint")


def _expected_for_failure(failure_type: str) -> str:
    return {
        "count_mismatch": "exact requested count",
        "color_mismatch": "requested color binding",
        "spatial_mismatch": "requested relative layout",
        "missing_object": "object visible",
        "extra_object": "no extra object",
    }.get(failure_type, "expected constraint")


def _detected_for_failure(failure_type: str) -> str:
    return {
        "count_mismatch": "wrong count",
        "color_mismatch": "wrong color",
        "spatial_mismatch": "wrong layout",
        "missing_object": "object missing",
        "extra_object": "extra object present",
    }.get(failure_type, "failed constraint")

