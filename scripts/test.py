#!/usr/bin/env python3
"""List GPT-like models from the configured OpenAI-compatible relay."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "https://skyapi.duckdns.org/v1"


def main() -> int:
    parser = argparse.ArgumentParser(description="List models from an OpenAI-compatible relay.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("GEN_RETRY_TEACHER_BASE_URL")
        or DEFAULT_BASE_URL,
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENAI_API_KEY") or os.environ.get("GEN_RETRY_TEACHER_API_KEY"),
    )
    parser.add_argument("--contains", default="gpt", help="Only print model ids containing this text.")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: set OPENAI_API_KEY or GEN_RETRY_TEACHER_API_KEY.", file=sys.stderr)
        return 2

    base_url = args.base_url.rstrip("/")
    try:
        response = get_json(f"{base_url}/models", api_key=args.api_key, timeout=args.timeout)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: GET {base_url}/models failed: {exc}", file=sys.stderr)
        return 1

    model_ids = extract_model_ids(response)
    needle = args.contains.lower()
    matched = [model_id for model_id in model_ids if needle in model_id.lower()]
    if matched:
        print(f"Models containing {args.contains!r}:")
        for model_id in matched:
            print(model_id)
    else:
        print(f"No model id contains {args.contains!r}.")
    return 0


def get_json(url: str, *, api_key: str, timeout: float) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:2000]}") from exc
    return json.loads(raw)


def extract_model_ids(data: Any) -> list[str]:
    rows = None
    if isinstance(data, dict):
        for key in ("data", "models", "model_list"):
            value = data.get(key)
            if isinstance(value, list):
                rows = value
                break
    elif isinstance(data, list):
        rows = data
    if not isinstance(rows, list):
        return []

    ids: list[str] = []
    for row in rows:
        if isinstance(row, str):
            ids.append(row)
        elif isinstance(row, dict):
            for key in ("id", "model", "name"):
                value = row.get(key)
                if isinstance(value, str):
                    ids.append(value)
                    break
    return sorted(ids)


if __name__ == "__main__":
    raise SystemExit(main())
