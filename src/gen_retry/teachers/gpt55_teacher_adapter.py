"""OpenAI-compatible GPT-5.5 teacher adapter."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from gen_retry.prompts.initial_plan_prompt import build_initial_plan_messages
from gen_retry.prompts.retry_replan_prompt import build_retry_replan_messages
from gen_retry.schemas.actions import (
    ActionValidationError,
    InitialPlanAction,
    RetryReplanAction,
)
from gen_retry.schemas.episode_schema import TeacherAction
from gen_retry.teachers.base import BaseTeacher


ENV_TEACHER_BASE_URL = "GEN_RETRY_TEACHER_BASE_URL"
ENV_TEACHER_API_KEY = "GEN_RETRY_TEACHER_API_KEY"
ENV_TEACHER_MODEL = "GEN_RETRY_TEACHER_MODEL"
ENV_TEACHER_LOG_DIR = "GEN_RETRY_TEACHER_LOG_DIR"
ENV_TEACHER_TIMEOUT = "GEN_RETRY_TEACHER_TIMEOUT"
ENV_TEACHER_MAX_RETRIES = "GEN_RETRY_TEACHER_MAX_RETRIES"


class GPT55TeacherAdapter(BaseTeacher):
    name = "gpt55"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        max_parse_retries: int = 1,
        log_dir: str | Path | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get(ENV_TEACHER_BASE_URL) or "").rstrip("/")
        self.api_key = api_key or os.environ.get(ENV_TEACHER_API_KEY) or ""
        self.model = model or os.environ.get(ENV_TEACHER_MODEL) or "gpt-5.5"
        self.timeout = _env_float(ENV_TEACHER_TIMEOUT, timeout)
        self.max_parse_retries = _env_int(ENV_TEACHER_MAX_RETRIES, max_parse_retries)
        self.max_http_retries = _env_int(ENV_TEACHER_MAX_RETRIES, 3)
        self.log_dir = Path(log_dir or os.environ.get(ENV_TEACHER_LOG_DIR) or "data/api_logs/teacher")

    def initial_plan(
        self,
        *,
        original_prompt: str,
        evaluator_type: str = "geneval",
        prompt_metadata: dict[str, Any] | None = None,
    ) -> InitialPlanAction:
        messages = build_initial_plan_messages(
            original_prompt=original_prompt,
            evaluator_type=evaluator_type,
            prompt_metadata=prompt_metadata,
        )
        text = self._call_json(messages, call_type="initial_plan")
        return parse_initial_plan_json(text)

    def retry_replan(self, state: dict[str, Any]) -> RetryReplanAction:
        memory = state.get("memory") if isinstance(state.get("memory"), dict) else {}
        messages = build_retry_replan_messages(
            original_prompt=str(state.get("original_prompt", "")),
            previous_initial_plan=dict(state.get("previous_initial_plan") or {}),
            previous_action=dict(state.get("previous_action") or {}),
            previous_prompt=str(state.get("previous_prompt", "")),
            previous_selected_skills=[
                str(item) for item in state.get("previous_selected_skills", []) if str(item).strip()
            ],
            normalized_eval_report=dict(state.get("normalized_eval_report") or {}),
            retry_history=[
                item for item in state.get("retry_history", []) if isinstance(item, dict)
            ],
            retry_budget_left=int(state.get("retry_budget_left", 0)),
            current_round=int(state.get("current_round", state.get("retry_round", 0))),
            best_so_far=dict(state.get("best_so_far") or memory.get("best_so_far") or {}),
            fixed_constraints=list(
                state.get("fixed_constraints") or memory.get("fixed_constraints") or []
            ),
            persistent_failures=list(
                state.get("persistent_failures") or memory.get("persistent_failures") or []
            ),
            new_failures=list(state.get("new_failures") or memory.get("new_failures") or []),
            regressed_constraints=list(
                state.get("regressed_constraints") or memory.get("regressed_constraints") or []
            ),
            score_delta_from_previous=float(
                state.get(
                    "score_delta_from_previous",
                    memory.get("score_delta_from_previous", 0.0),
                )
            ),
            score_delta_from_best=float(
                state.get("score_delta_from_best", memory.get("score_delta_from_best", 0.0))
            ),
            branch_source=str(state.get("branch_source", "latest")),
            branch_source_round=int(state.get("branch_source_round", 0)),
            available_skills=state.get("available_skills"),
        )
        text = self._call_json(messages, call_type="retry_replan")
        return parse_retry_replan_json(text)

    def act(self, state: dict[str, Any]) -> TeacherAction:
        raise NotImplementedError("GPT55TeacherAdapter uses initial_plan/retry_replan, not legacy act()")

    def _call_json(self, messages: list[dict[str, str]], *, call_type: str) -> str:
        if not self.base_url:
            raise ValueError(f"{ENV_TEACHER_BASE_URL} is required")
        if not self.api_key:
            raise ValueError(f"{ENV_TEACHER_API_KEY} is required")
        last_text = ""
        for attempt in range(self.max_parse_retries + 1):
            if attempt:
                messages = _add_repair_instruction(messages, last_text)
            response = self._post_chat(messages)
            self._log_raw_response(call_type, response)
            last_text = _extract_content(response)
            try:
                if call_type == "initial_plan":
                    parse_initial_plan_json(last_text)
                else:
                    parse_retry_replan_json(last_text)
                return last_text
            except (json.JSONDecodeError, ActionValidationError, ValueError):
                if attempt >= self.max_parse_retries:
                    raise
        return last_text

    def _post_chat(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        body = json.dumps(payload).encode("utf-8")
        url = f"{self.base_url}/chat/completions"
        last_error: BaseException | None = None
        for attempt in range(1, self.max_http_retries + 1):
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
                last_error = RuntimeError(f"teacher API HTTP {exc.code}: {error_body[:2000]}")
                if exc.code < 500 and exc.code != 429:
                    raise last_error from exc
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            if attempt < self.max_http_retries:
                time.sleep(min(8.0, 0.5 * (2 ** (attempt - 1))))
        else:
            raise RuntimeError(f"POST {url} failed after {self.max_http_retries} attempt(s): {last_error}") from last_error
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise RuntimeError("teacher API response must be a JSON object")
        return data

    def _log_raw_response(self, call_type: str, response: dict[str, Any]) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        path = self.log_dir / f"{int(time.time() * 1000)}_{call_type}.json"
        path.write_text(json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def parse_initial_plan_json(text: str) -> InitialPlanAction:
    payload = _json_from_text(text)
    return InitialPlanAction.from_dict(payload)


def parse_retry_replan_json(text: str) -> RetryReplanAction:
    payload = _json_from_text(text)
    return RetryReplanAction.from_dict(payload)


def _json_from_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("teacher response must be a JSON object")
    return payload


def _extract_content(response: dict[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"unexpected teacher API response shape: {response}") from exc
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _add_repair_instruction(messages: list[dict[str, str]], previous_text: str) -> list[dict[str, str]]:
    repaired = list(messages)
    repaired.append(
        {
            "role": "user",
            "content": (
                "The previous response was not valid JSON for the requested schema. "
                "Return only one corrected JSON object. Previous response: "
                + previous_text[:2000]
            ),
        }
    )
    return repaired


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if not value:
        return default
    return float(value)


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    return int(value)
