"""Evaluator interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod

from gen_retry.schemas.episode_schema import NormalizedGenevalReport
from gen_retry.schemas.reports import NormalizedEvalReport


class BaseImageEvaluator(ABC):
    name = "base_evaluator"

    @abstractmethod
    def evaluate(self, original_prompt: str, image_path: str) -> NormalizedEvalReport:
        """Evaluate an image against the original prompt."""


class BaseEvaluator(ABC):
    @abstractmethod
    def evaluate(self, original_prompt: str, image_path: str) -> NormalizedGenevalReport:
        """Evaluate an image against the original prompt."""
