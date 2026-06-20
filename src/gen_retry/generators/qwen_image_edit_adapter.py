"""Qwen-Image-Edit adapter skeleton.

This file intentionally does not call real APIs in local tests. Wire the actual
HTTP client in a controlled environment.
"""

from __future__ import annotations

import os
from pathlib import Path

from gen_retry.generators.base import BaseRetryExecutor


ENV_QWEN_IMAGE_EDIT_ENDPOINT = "GEN_RETRY_QWEN_IMAGE_EDIT_ENDPOINT"
ENV_QWEN_IMAGE_EDIT_API_KEY = "GEN_RETRY_QWEN_IMAGE_EDIT_API_KEY"


class QwenImageEditAdapter(BaseRetryExecutor):
    def __init__(self, image_dir: str | Path = "data/images") -> None:
        self.image_dir = Path(image_dir)
        self.endpoint = os.environ.get(ENV_QWEN_IMAGE_EDIT_ENDPOINT, "").strip()
        self.api_key = os.environ.get(ENV_QWEN_IMAGE_EDIT_API_KEY, "").strip()

    def edit(self, image_path: str, instruction: str, episode_id: str, round_id: int) -> str:
        _ = (image_path, instruction, episode_id, round_id)
        # TODO: call Qwen-Image-Edit-2511 or another image edit endpoint.
        # The API key must come from GEN_RETRY_QWEN_IMAGE_EDIT_API_KEY.
        # Save the returned image under self.image_dir and return its path.
        raise NotImplementedError("Qwen-Image-Edit adapter is scaffolded but not implemented")

    def regenerate(self, prompt: str, episode_id: str, round_id: int) -> str:
        _ = (prompt, episode_id, round_id)
        # TODO: optionally wire a text-to-image regeneration endpoint.
        raise NotImplementedError("Qwen-Image-Edit regeneration is not implemented")

