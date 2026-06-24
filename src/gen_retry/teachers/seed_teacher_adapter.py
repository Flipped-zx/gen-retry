"""Seed2.0-style teacher adapter scaffold."""

from __future__ import annotations

from gen_retry.teachers.gpt55_teacher_adapter import GPT55TeacherAdapter


class SeedTeacherAdapter(GPT55TeacherAdapter):
    """Same planner interface as GPT55TeacherAdapter, with Seed defaults."""

    name = "seed_teacher_adapter"

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("model", "doubao-seed-2-0-pro")
        super().__init__(**kwargs)
