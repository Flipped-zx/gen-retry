"""OpenAI-compatible teacher client with dry-run support."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from gen_retry.teacher.build_retry_action import build_mock_retry_action
from gen_retry.teacher.prompts import build_teacher_messages
from gen_retry.teacher.schemas import TeacherRetryAction, parse_teacher_action_text


ENV_BASE_URL = "GEN_RETRY_TEACHER_BASE_URL"
ENV_API_KEY = "GEN_RETRY_TEACHER_API_KEY"
ENV_MODEL = "GEN_RETRY_TEACHER_MODEL"
ENV_TIMEOUT = "GEN_RETRY_TEACHER_TIMEOUT"
ENV_MAX_RETRIES = "GEN_RETRY_TEACHER_MAX_RETRIES"


class TeacherClientError(RuntimeError):
    """Teacher client call failed."""


@dataclass(frozen=True)
class TeacherClientConfig:
    base_url: str
    api_key: str
    model: str = "gpt-5.5"
    timeout: float = 120.0
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> "TeacherClientConfig":
        timeout_raw = os.environ.get(ENV_TIMEOUT, "120")
        retries_raw = os.environ.get(ENV_MAX_RETRIES, "3")
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = 120.0
        try:
            max_retries = max(1, int(retries_raw))
        except ValueError:
            max_retries = 3
        return cls(
            base_url=os.environ.get(ENV_BASE_URL, "https://api.openai.com/v1").strip(),
            api_key=os.environ.get(ENV_API_KEY, "").strip(),
            model=os.environ.get(ENV_MODEL, "gpt-5.5").strip() or "gpt-5.5",
            timeout=timeout,
            max_retries=max_retries,
        )


class TeacherClient:
    """Minimal stdlib OpenAI-compatible client.

    The real API path is intentionally not used by tests. Use dry-run mode for
    local development without an API key.
    """

    def __init__(self, config: TeacherClientConfig | None = None) -> None:
        self.config = config or TeacherClientConfig.from_env()

    def generate_retry_action(
        self,
        *,
        diagnostic: dict[str, Any],
        normalized_diagnostic: dict[str, Any],
        first_attempt_prompt: str | None = None,
        dry_run: bool = False,
    ) -> TeacherRetryAction:
        if dry_run:
            return build_mock_retry_action(
                diagnostic,
                normalized_diagnostic=normalized_diagnostic,
                first_attempt=first_attempt_prompt,
            )
        if not self.config.api_key:
            raise TeacherClientError(f"{ENV_API_KEY} is required unless dry_run is enabled")

        messages = build_teacher_messages(
            diagnostic=diagnostic,
            normalized_diagnostic=normalized_diagnostic,
            first_attempt_prompt=first_attempt_prompt,
        )
        try:
            content = self._call_responses(messages)
        except TeacherClientError:
            content = self._call_chat_completions(messages)
        return parse_teacher_action_text(content)

    def _call_responses(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.config.model,
            "input": messages,
            "temperature": 0,
        }
        data = self._post_json("/responses", payload)
        text = _extract_responses_text(data)
        if not text:
            raise TeacherClientError("Responses API returned no text")
        return text

    def _call_chat_completions(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        data = self._post_json("/chat/completions", payload)
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TeacherClientError("Chat Completions API returned no message content") from exc
        if not isinstance(text, str) or not text.strip():
            raise TeacherClientError("Chat Completions API returned empty content")
        return text

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        base_url = self.config.base_url.rstrip("/")
        url = base_url + path
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        last_error: BaseException | None = None
        for attempt in range(1, self.config.max_retries + 1):
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                    raw = response.read().decode("utf-8")
                    return json.loads(raw)
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code in (400, 404, 405, 422):
                    break
            except Exception as exc:
                last_error = exc
            if attempt < self.config.max_retries:
                time.sleep(min(8.0, 0.5 * (2 ** (attempt - 1))))
        raise TeacherClientError(f"POST {url} failed: {last_error}")


def _extract_responses_text(data: dict[str, Any]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    chunks: list[str] = []
    for item in data.get("output", []) if isinstance(data.get("output"), list) else []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks).strip()
