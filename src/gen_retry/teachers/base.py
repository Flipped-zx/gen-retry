"""Teacher policy interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from gen_retry.schemas.episode_schema import TeacherAction


class BaseTeacher(ABC):
    @abstractmethod
    def act(self, state: dict[str, Any]) -> TeacherAction:
        """Choose the next retry action from the current state."""

