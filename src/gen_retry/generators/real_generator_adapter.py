"""Stable wrapper for real prompt-to-image generation backends."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from gen_retry.generators.base import BaseGenerator


ENV_IMAGE_BASE_URL = "GEN_RETRY_IMAGE_BASE_URL"
ENV_IMAGE_API_KEY = "GEN_RETRY_IMAGE_API_KEY"
ENV_IMAGE_MODEL = "GEN_RETRY_IMAGE_MODEL"
ENV_IMAGE_SIZE = "GEN_RETRY_IMAGE_SIZE"
ENV_IMAGE_QUALITY = "GEN_RETRY_IMAGE_QUALITY"
ENV_IMAGE_TIMEOUT = "GEN_RETRY_IMAGE_TIMEOUT"
ENV_IMAGE_MAX_RETRIES = "GEN_RETRY_IMAGE_MAX_RETRIES"
ENV_IMAGE_EXTRA_JSON = "GEN_RETRY_IMAGE_EXTRA_JSON"


class RealGeneratorAdapter(BaseGenerator):
    """Dispatch prompt-to-image requests to a configured backend.

    The retry collector only depends on this stable interface. Backend-specific
    implementations can be filled in without changing episode schemas.
    """

    def __init__(self, backend: str | None = None) -> None:
        self.backend = (backend or os.environ.get("GEN_RETRY_GENERATOR_BACKEND") or "gpt_image").strip()
        self.base_url = (os.environ.get(ENV_IMAGE_BASE_URL) or "").rstrip("/")
        self.api_key = os.environ.get(ENV_IMAGE_API_KEY) or ""
        self.model = os.environ.get(ENV_IMAGE_MODEL) or "gpt-image-2"
        self.name = "gpt_image2" if self.backend == "gpt_image" and self.model == "gpt-image-2" else f"real_generator:{self.backend}"
        self.size = _env_optional_string(ENV_IMAGE_SIZE) or "1024x1024"
        self.quality = _env_optional_string(ENV_IMAGE_QUALITY) or ""
        self.timeout = _env_float(ENV_IMAGE_TIMEOUT, 180.0)
        self.max_retries = _env_int(ENV_IMAGE_MAX_RETRIES, 3)
        self.extra_payload = _env_json_object(ENV_IMAGE_EXTRA_JSON)

    def generate(self, prompt: str, output_path: str, metadata: dict[str, Any] | None = None) -> str:
        if self.backend == "gpt_image":
            return self._generate_openai_image(prompt, output_path, metadata=metadata)
        if self.backend in {"gemini_image", "nano"}:
            raise NotImplementedError(f"backend {self.backend!r} is not implemented")
        raise ValueError(f"unsupported generator backend: {self.backend}")

    def _generate_openai_image(
        self,
        prompt: str,
        output_path: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not self.base_url:
            raise ValueError(f"{ENV_IMAGE_BASE_URL} is required")
        if not self.api_key:
            raise ValueError(f"{ENV_IMAGE_API_KEY} is required")

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": self.size,
        }
        if self.quality:
            payload["quality"] = self.quality
        payload.update(self.extra_payload)

        response = self._post_images_generation(payload)
        image_bytes = _extract_image_bytes(response, timeout=self.timeout)

        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(image_bytes)
        _write_sidecar(
            target,
            {
                "backend": self.backend,
                "model": self.model,
                "prompt": prompt,
                "payload": _redact_payload(payload),
                "metadata": metadata or {},
                "response_metadata": _response_metadata(response),
            },
        )
        return str(target)

    def _post_images_generation(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        url = f"{self.base_url}/images/generations"
        last_error: BaseException | None = None
        for attempt in range(1, self.max_retries + 1):
            request = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                    break
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"image API HTTP {exc.code}: {error_body[:2000]}")
                if exc.code < 500 and exc.code != 429:
                    raise last_error from exc
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            if attempt < self.max_retries:
                import time

                time.sleep(min(8.0, 0.5 * (2 ** (attempt - 1))))
        else:
            raise RuntimeError(f"POST {url} failed after {self.max_retries} attempt(s): {last_error}") from last_error
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise RuntimeError("image API response must be a JSON object")
        return data


def _extract_image_bytes(response: dict[str, Any], *, timeout: float) -> bytes:
    data = response.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            encoded = first.get("b64_json") or first.get("base64") or first.get("b64")
            if isinstance(encoded, str) and encoded.strip():
                return _decode_base64_image(encoded)
            url = first.get("url") or first.get("image_url")
            if isinstance(url, str) and url.strip():
                return _download_image_url(url, timeout=timeout)

    image = response.get("image")
    if isinstance(image, str) and image.strip():
        return _decode_base64_image(image)

    raise RuntimeError(f"could not find image bytes in response keys: {sorted(response)}")


def _download_image_url(url: str, *, timeout: float) -> bytes:
    if url.startswith("data:image/"):
        _, encoded = url.split(",", 1)
        return _decode_base64_image(encoded)
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def _decode_base64_image(value: str) -> bytes:
    encoded = value.strip()
    if encoded.startswith("data:image/"):
        _, encoded = encoded.split(",", 1)
    return base64.b64decode(encoded)


def _write_sidecar(image_path: Path, metadata: dict[str, Any]) -> None:
    sidecar = image_path.with_suffix(image_path.suffix + ".json")
    sidecar.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _response_metadata(response: dict[str, Any]) -> dict[str, Any]:
    keys = {"created", "model", "usage"}
    return {key: response[key] for key in keys if key in response}


def _redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "api_key"}


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if not value:
        return default
    return float(value)


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    return max(1, int(value))


def _env_optional_string(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value.lower() in {"", "none", "null"}:
        return ""
    return value


def _env_json_object(name: str) -> dict[str, Any]:
    value = os.environ.get(name)
    if not value:
        return {}
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be a JSON object")
    return payload
