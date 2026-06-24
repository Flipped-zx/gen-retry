"""Local Geneval evaluator adapter scaffold."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from gen_retry.evaluators.base import BaseImageEvaluator
from gen_retry.evaluators.normalizer import normalize_geneval_report
from gen_retry.schemas.reports import NormalizedEvalReport


class GenevalAdapter(BaseImageEvaluator):
    name = "geneval"

    def __init__(self, command_template: str | None = None) -> None:
        self.command_template = command_template

    def evaluate(self, original_prompt: str, image_path: str) -> NormalizedEvalReport:
        if not self.command_template:
            raise NotImplementedError("GenevalAdapter requires a command_template or project-specific implementation")
        output_path = Path(image_path).with_suffix(".geneval.json")
        command = self.command_template.format(
            prompt=original_prompt,
            image_path=image_path,
            output_path=str(output_path),
        )
        subprocess.run(command, shell=True, check=True)
        raw = json.loads(output_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{output_path} must contain a JSON object")
        return normalize_geneval_report(raw)
