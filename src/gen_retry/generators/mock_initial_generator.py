"""Mock image generator and retry executor."""

from __future__ import annotations

from pathlib import Path

from gen_retry.generators.base import BaseInitialGenerator, BaseRetryExecutor


class MockInitialGenerator(BaseInitialGenerator):
    """Create deterministic placeholder image files without calling a model."""

    def __init__(self, image_dir: str | Path = "data/images") -> None:
        self.image_dir = Path(image_dir)

    def generate(self, prompt: str, episode_id: str, round_id: int) -> str:
        path = self.image_dir / f"{episode_id}_attempt_{round_id}.png"
        _write_placeholder(path, f"mock initial image\nprompt: {prompt}\n")
        return str(path)


class MockRetryExecutor(BaseRetryExecutor):
    """Create deterministic placeholder retry images without external APIs."""

    def __init__(self, image_dir: str | Path = "data/images") -> None:
        self.image_dir = Path(image_dir)

    def edit(self, image_path: str, instruction: str, episode_id: str, round_id: int) -> str:
        path = self.image_dir / f"{episode_id}_attempt_{round_id}.png"
        _write_placeholder(
            path,
            "mock edited image\n"
            f"source_image: {image_path}\n"
            f"instruction: {instruction}\n",
        )
        return str(path)

    def regenerate(self, prompt: str, episode_id: str, round_id: int) -> str:
        path = self.image_dir / f"{episode_id}_attempt_{round_id}.png"
        _write_placeholder(path, f"mock regenerated image\nprompt: {prompt}\n")
        return str(path)


def _write_placeholder(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

