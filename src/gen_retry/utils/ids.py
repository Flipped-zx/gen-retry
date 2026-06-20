"""Identifier helpers."""

from __future__ import annotations

import hashlib
import uuid


def make_episode_id(prompt: str, index: int | None = None) -> str:
    if index is None:
        return "episode_" + uuid.uuid4().hex[:12]
    digest = hashlib.sha1(f"{index}:{prompt}".encode("utf-8")).hexdigest()[:12]
    return f"episode_{index:06d}_{digest}"

