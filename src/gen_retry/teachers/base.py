"""Teacher planner interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from gen_retry.schemas.actions import InitialPlanAction, RetryReplanAction
from gen_retry.schemas.episode_schema import TeacherAction


class BaseTeacher(ABC):
    name = "base_teacher"

    @abstractmethod
    def initial_plan(
        self,
        *,
        original_prompt: str,
        evaluator_type: str = "geneval",
        prompt_metadata: dict[str, Any] | None = None,
    ) -> InitialPlanAction:
        """Plan the first generation prompt."""

    @abstractmethod
    def retry_replan(self, state: dict[str, Any]) -> RetryReplanAction:
        """Plan a regeneration prompt from normalized verifier feedback."""

    @abstractmethod
    def act(self, state: dict[str, Any]) -> TeacherAction:
        """Legacy policy entrypoint kept for older collectors."""
