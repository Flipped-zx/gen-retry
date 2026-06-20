"""GPT-5.5 teacher adapter skeleton.

The real API call is intentionally not implemented for local tests.
"""

from __future__ import annotations

import json
import os
from typing import Any

from gen_retry.schemas.episode_schema import TeacherAction
from gen_retry.teachers.base import BaseTeacher
from gen_retry.teachers.teacher_prompt import build_teacher_payload


ENV_TEACHER_BASE_URL = "GEN_RETRY_TEACHER_BASE_URL"
ENV_TEACHER_API_KEY = "GEN_RETRY_TEACHER_API_KEY"
ENV_TEACHER_MODEL = "GEN_RETRY_TEACHER_MODEL"


class GPT55TeacherAdapter(BaseTeacher):
    def __init__(self) -> None:
        self.base_url = os.environ.get(ENV_TEACHER_BASE_URL, "").strip()
        self.api_key = os.environ.get(ENV_TEACHER_API_KEY, "").strip()
        self.model = os.environ.get(ENV_TEACHER_MODEL, "gpt-5.5").strip() or "gpt-5.5"

    def act(self, state: dict[str, Any]) -> TeacherAction:
        messages = build_teacher_payload(state)
        _ = messages
        # TODO: send messages to an OpenAI-compatible relay using self.base_url,
        # self.api_key, and self.model. Do not log or persist the API key.
        # Parse the response with parse_teacher_action_json.
        raise NotImplementedError("GPT-5.5 teacher adapter is scaffolded but not implemented")


def parse_teacher_action_json(text: str) -> TeacherAction:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("teacher response must be a JSON object")
    action = TeacherAction.from_dict(payload)
    validate_teacher_action(action)
    return action


def validate_teacher_action(action: TeacherAction) -> None:
    if action.decision not in {"retry", "submit", "abandon"}:
        raise ValueError(f"invalid teacher decision: {action.decision}")
    if action.decision == "retry":
        if action.action_type not in {"image_edit", "rewrite_prompt"}:
            raise ValueError("retry action must use image_edit or rewrite_prompt")
        if not action.edit_instruction and not action.retry_prompt:
            raise ValueError("retry action requires edit_instruction or retry_prompt")

