"""Local GenEval2 evaluator adapter."""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

from gen_retry.evaluators.base import BaseImageEvaluator
from gen_retry.evaluators.geneval2_result_normalizer import (
    load_geneval2_score_rows,
    normalize_geneval2_score_list,
)
from gen_retry.evaluators.normalizer import normalize_geneval2_report
from gen_retry.schemas.reports import NormalizedEvalReport


class Geneval2Adapter(BaseImageEvaluator):
    name = "geneval2"

    def __init__(
        self,
        command_template: str | None = None,
        *,
        score_list_path: str | Path | None = None,
        benchmark_data_path: str | Path | None = None,
        aggregate_by: str = "prompt_id",
    ) -> None:
        self.command_template = command_template
        self.score_list_path = Path(score_list_path) if score_list_path else None
        self.benchmark_data_path = Path(benchmark_data_path) if benchmark_data_path else None
        self.aggregate_by = aggregate_by
        self._reports: dict[str, NormalizedEvalReport] | None = None

    def evaluate(self, original_prompt: str, image_path: str) -> NormalizedEvalReport:
        if self.score_list_path:
            return self._evaluate_from_score_list(original_prompt, image_path)
        if not self.command_template:
            raise NotImplementedError(
                "Geneval2Adapter requires command_template or score_list_path"
            )
        output_path = Path(image_path).with_suffix(".geneval2.json")
        command = self.command_template.format(
            prompt=shlex.quote(original_prompt),
            image_path=shlex.quote(image_path),
            output_path=shlex.quote(str(output_path)),
            prompt_raw=original_prompt,
            image_path_raw=image_path,
            output_path_raw=str(output_path),
        )
        subprocess.run(command, shell=True, check=True)
        raw = json.loads(output_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            reports = normalize_geneval2_score_list(
                load_geneval2_score_rows(output_path, benchmark_data=self.benchmark_data_path),
                aggregate_by=self.aggregate_by,
            )
            return _select_report(reports, original_prompt=original_prompt, image_path=image_path)
        if not isinstance(raw, dict):
            raise ValueError(f"{output_path} must contain a JSON object or list")
        return normalize_geneval2_report(raw)

    def _evaluate_from_score_list(self, original_prompt: str, image_path: str) -> NormalizedEvalReport:
        if self._reports is None:
            rows = load_geneval2_score_rows(
                self.score_list_path,
                benchmark_data=self.benchmark_data_path,
            )
            self._reports = normalize_geneval2_score_list(rows, aggregate_by=self.aggregate_by)
        return _select_report(self._reports, original_prompt=original_prompt, image_path=image_path)


def _select_report(
    reports: dict[str, NormalizedEvalReport],
    *,
    original_prompt: str,
    image_path: str,
) -> NormalizedEvalReport:
    candidates = [
        image_path,
        str(Path(image_path)),
        Path(image_path).name,
        original_prompt,
    ]
    for key in candidates:
        if key in reports:
            return reports[key]
    if len(reports) == 1:
        return next(iter(reports.values()))
    raise KeyError(
        "could not select GenEval2 report for "
        f"prompt={original_prompt!r}, image_path={image_path!r}; available keys={list(reports)[:10]}"
    )
