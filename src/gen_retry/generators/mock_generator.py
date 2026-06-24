"""Mock regeneration-only image generator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gen_retry.generators.base import BaseGenerator


class MockGenerator(BaseGenerator):
    name = "mock_generator"

    def generate(self, prompt: str, output_path: str, metadata: dict[str, Any] | None = None) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        details = metadata or {}
        path.write_text(
            "mock generated image\n"
            f"prompt: {prompt}\n"
            f"metadata: {details}\n",
            encoding="utf-8",
        )
        return str(path)
