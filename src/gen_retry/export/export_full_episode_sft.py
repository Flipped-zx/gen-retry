"""Export full raw episodes as JSONL for inspection or future SFT formats."""

from __future__ import annotations

from pathlib import Path

from gen_retry.utils.io import read_json, write_jsonl


def export_full_episode_sft(
    episodes_dir: str | Path = "data/raw_episodes",
    output: str | Path = "data/sft/retry_full_episode_sft.jsonl",
) -> int:
    rows = []
    for path in sorted(Path(episodes_dir).glob("*.json")):
        rows.append(read_json(path))
    return write_jsonl(output, rows)

