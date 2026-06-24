"""Generator interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseGenerator(ABC):
    name = "base_generator"

    @abstractmethod
    def generate(self, prompt: str, output_path: str, metadata: dict[str, Any] | None = None) -> str:
        """Generate an image from a prompt and return the saved image path."""


class BaseInitialGenerator(ABC):
    @abstractmethod
    def generate(self, prompt: str, episode_id: str, round_id: int) -> str:
        """Generate the first image and return its path."""


class BaseRetryExecutor(ABC):
    @abstractmethod
    def edit(self, image_path: str, instruction: str, episode_id: str, round_id: int) -> str:
        """Edit an existing image and return the new image path."""

    def regenerate(self, prompt: str, episode_id: str, round_id: int) -> str:
        """Optionally regenerate from a prompt."""
        raise NotImplementedError("This retry executor does not support regeneration")
