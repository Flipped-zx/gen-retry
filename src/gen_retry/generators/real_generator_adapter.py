"""Stable wrapper for real prompt-to-image generation backends."""

from __future__ import annotations

import os
from typing import Any

from gen_retry.generators.base import BaseGenerator


class RealGeneratorAdapter(BaseGenerator):
    """Dispatch prompt-to-image requests to a configured backend.

    The retry collector only depends on this stable interface. Backend-specific
    implementations can be filled in without changing episode schemas.
    """

    def __init__(self, backend: str | None = None) -> None:
        self.backend = (backend or os.environ.get("GEN_RETRY_GENERATOR_BACKEND") or "gpt_image").strip()
        self.name = f"real_generator:{self.backend}"

    def generate(self, prompt: str, output_path: str, metadata: dict[str, Any] | None = None) -> str:
        if self.backend in {"gpt_image", "gemini_image", "nano"}:
            raise NotImplementedError(
                f"backend {self.backend!r} is scaffolded; implement API call and save image to {output_path}"
            )
        raise ValueError(f"unsupported generator backend: {self.backend}")
