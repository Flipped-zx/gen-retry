"""Evaluator interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from gen_retry.schemas.episode_schema import NormalizedGenevalReport


class BaseEvaluator(ABC):
    @abstractmethod
    def evaluate(self, original_prompt: str, image_path: str) -> NormalizedGenevalReport:
        """Evaluate an image against the original prompt."""

