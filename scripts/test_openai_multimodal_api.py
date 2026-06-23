#!/usr/bin/env python3
"""Smoke test an OpenAI-compatible multimodal chat API."""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://poloai.top/v1"
DEFAULT_MODEL = "gemini-3.1-pro-preview"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List models and test OpenAI-compatible multimodal chat completions."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL,
        help="OpenAI-compatible base URL, e.g. https://generativelanguage.googleapis.com/v1beta/openai",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY"),
        help="API key. Defaults to OPENAI_API_KEY or GEMINI_API_KEY.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL,
        help=f"Model id to test. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument("--image", help="Optional local image path. If omitted, a small test image is generated.")
    parser.add_argument("--prompt", default="Describe this image in one short sentence.")
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--skip-models", action="store_true", help="Skip GET /models.")
    parser.add_argument("--models-only", action="store_true", help="Only list models; do not run chat test.")
    parser.add_argument("--debug-models", action="store_true", help="Print raw /models response when no ids are found.")
    parser.add_argument("--debug-chat", action="store_true", help="Print raw chat/completions response.")
    parser.add_argument("--text-only", action="store_true", help="Send a text-only chat request instead of an image request.")
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: API key is required. Set OPENAI_API_KEY or GEMINI_API_KEY, or pass --api-key.", file=sys.stderr)
        return 2

    base_url = args.base_url.rstrip("/")

    if not args.skip_models:
        print(f"[models] GET {base_url}/models")
        try:
            model_response = fetch_models(base_url=base_url, api_key=args.api_key, timeout=args.timeout)
            models = extract_model_ids(model_response)
            if models:
                print(f"[models] {len(models)} model id(s):")
                for model_id in models:
                    marker = "  *" if model_id == args.model else "  -"
                    print(f"{marker} {model_id}")
                if args.model not in models:
                    print(f"[models] warning: requested model {args.model!r} was not returned by /models")
            else:
                print("[models] /models returned no ids")
                if args.debug_models:
                    print("[models] raw response:")
                    print(json.dumps(model_response, ensure_ascii=False, indent=2)[:8000])
        except Exception as exc:  # noqa: BLE001
            print(f"[models] failed: {exc}")
            if args.models_only:
                return 1

    if args.models_only:
        return 0

    print(f"[chat] POST {base_url}/chat/completions model={args.model}")
    if args.text_only:
        user_content: str | list[dict[str, Any]] = args.prompt
    else:
        image_b64, mime_type = load_or_create_image(args.image)
        user_content = [
            {"type": "text", "text": args.prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{image_b64}",
                },
            },
        ]
    payload = {
        "model": args.model,
        "messages": [
            {
                "role": "user",
                "content": user_content,
            }
        ],
        "max_tokens": args.max_tokens,
    }
    try:
        response = post_json(
            url=f"{base_url}/chat/completions",
            api_key=args.api_key,
            payload=payload,
            timeout=args.timeout,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[chat] failed: {exc}", file=sys.stderr)
        return 1

    content = extract_chat_content(response)
    print("[chat] ok")
    if args.debug_chat:
        print("[chat] raw response:")
        print(json.dumps(response, ensure_ascii=False, indent=2)[:8000])
    print("[chat] response:")
    print(content or json.dumps(response, ensure_ascii=False, indent=2)[:4000])
    return 0


def fetch_models(*, base_url: str, api_key: str, timeout: float) -> Any:
    return get_json(url=f"{base_url}/models", api_key=api_key, timeout=timeout)


def extract_model_ids(data: Any) -> list[str]:
    rows = None
    if isinstance(data, dict):
        for key in ("data", "models", "model_list"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
    elif isinstance(data, list):
        rows = data
    if not isinstance(rows, list):
        return []
    ids = []
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


def get_json(*, url: str, api_key: str, timeout: float) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    return read_json_response(request, timeout=timeout)


def post_json(*, url: str, api_key: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    return read_json_response(request, timeout=timeout)


def read_json_response(request: urllib.request.Request, *, timeout: float) -> Any:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:2000]}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"expected JSON response, got: {raw[:2000]}") from exc


def load_or_create_image(path: str | None) -> tuple[str, str]:
    if path:
        image_path = Path(path)
        raw = image_path.read_bytes()
        suffix = image_path.suffix.lower()
        mime_type = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
        return base64.b64encode(raw).decode("ascii"), mime_type
    raw = create_test_png()
    return base64.b64encode(raw).decode("ascii"), "image/png"


def create_test_png() -> bytes:
    try:
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (256, 256), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle([30, 30, 120, 120], fill="red")
        draw.ellipse([145, 95, 225, 175], fill="blue")
        draw.text((30, 205), "red square + blue circle", fill="black")
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        # 1x1 red PNG fallback.
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR42mP8z8BQDwAFgwJ/lP8eJwAAAABJRU5ErkJggg=="
        )


def extract_chat_content(response: dict[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


if __name__ == "__main__":
    raise SystemExit(main())
