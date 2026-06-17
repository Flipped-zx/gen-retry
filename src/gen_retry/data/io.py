"""Small JSON and JSONL helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def read_json_or_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read a JSON object, JSON array, or JSONL file into a list of objects."""

    source = Path(path)
    raw = source.read_text(encoding="utf-8").strip()
    if not raw:
        return []

    if source.suffix.lower() == ".jsonl":
        return _read_jsonl(source, raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _read_jsonl(source, raw)
    return _coerce_records(source, data)


def _coerce_records(source: Path, data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        return [data]
    if not isinstance(data, list):
        raise ValueError(f"{source} JSON root must be an object or array")
    out: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"{source} item {index} is not an object")
        out.append(item)
    return out


def _read_jsonl(source: Path, raw: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for lineno, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError(f"{source}:{lineno} JSONL item is not an object")
        out.append(item)
    return out


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> int:
    """Write records to JSONL and return the number of written rows."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
            count += 1
    return count
