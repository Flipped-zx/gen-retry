"""Collector for mock or real visual retry episodes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gen_retry.evaluators.base import BaseEvaluator
from gen_retry.filters.filter_episodes import classify_transition, has_new_critical_failure, is_passed
from gen_retry.generators.base import BaseInitialGenerator, BaseRetryExecutor
from gen_retry.schemas.episode_schema import Attempt, Episode, NormalizedGenevalReport, TeacherAction
from gen_retry.skills.skill_library import available_skills
from gen_retry.teachers.base import BaseTeacher
from gen_retry.utils.ids import make_episode_id
from gen_retry.utils.io import write_json


class RetryEpisodeCollector:
    def __init__(
        self,
        *,
        initial_generator: BaseInitialGenerator,
        retry_executor: BaseRetryExecutor,
        evaluator: BaseEvaluator,
        teacher: BaseTeacher,
        output_dir: str | Path = "data/raw_episodes",
    ) -> None:
        self.initial_generator = initial_generator
        self.retry_executor = retry_executor
        self.evaluator = evaluator
        self.teacher = teacher
        self.output_dir = Path(output_dir)

    def run_episode(
        self,
        prompt: str,
        *,
        max_retry: int = 2,
        pass_threshold: float = 0.95,
        episode_id: str | None = None,
        prompt_metadata: dict[str, Any] | None = None,
    ) -> Episode:
        episode_id = episode_id or make_episode_id(prompt)
        image_path = self.initial_generator.generate(prompt, episode_id, 0)
        report = self.evaluator.evaluate(prompt, image_path)
        initial_attempt = Attempt(
            round=0,
            attempt_type="initial_generation",
            prompt=prompt,
            image_path=image_path,
            geneval_report=report,
            metadata={"retry_budget_left": max_retry},
        )
        episode = Episode(
            id=episode_id,
            original_prompt=prompt,
            attempts=[initial_attempt],
            final_outcome="unknown",
            metadata={
                "max_retry": max_retry,
                "pass_threshold": pass_threshold,
                "prompt_metadata": prompt_metadata or {},
            },
        )

        if is_passed(report, pass_threshold=pass_threshold):
            submit = self.teacher.act(self._state(episode, initial_attempt, max_retry))
            initial_attempt.teacher_action = submit
            initial_attempt.metadata["transition_outcome"] = "pass_without_retry"
            episode.final_outcome = "pass_without_retry"
            self.save_episode(episode)
            return episode

        current_attempt = initial_attempt
        retries_used = 0
        while retries_used < max_retry:
            retry_budget_left = max_retry - retries_used
            action = self.teacher.act(self._state(episode, current_attempt, retry_budget_left))
            current_attempt.teacher_action = action

            if action.decision == "submit":
                episode.final_outcome = (
                    "teacher_submit"
                    if is_passed(current_attempt.geneval_report, pass_threshold=pass_threshold)
                    else "invalid_submit"
                )
                break
            if action.decision == "abandon":
                episode.final_outcome = "abandon"
                break

            retries_used += 1
            next_round = len(episode.attempts)
            retry_prompt = action.retry_prompt or current_attempt.prompt
            if action.action_type == "rewrite_prompt":
                next_image_path = self.retry_executor.regenerate(retry_prompt, episode.id, next_round)
                attempt_type = "retry_regeneration"
            else:
                next_image_path = self.retry_executor.edit(
                    current_attempt.image_path,
                    action.edit_instruction,
                    episode.id,
                    next_round,
                )
                attempt_type = "retry_edit"
            after_report = self.evaluator.evaluate(prompt, next_image_path)
            transition = classify_transition(
                current_attempt.geneval_report,
                after_report,
                pass_threshold=pass_threshold,
            )
            current_attempt.metadata["transition_outcome"] = transition
            current_attempt.metadata["new_critical_failures"] = has_new_critical_failure(
                current_attempt.geneval_report,
                after_report,
            )

            retry_attempt = Attempt(
                round=next_round,
                attempt_type=attempt_type,
                prompt=retry_prompt,
                image_path=next_image_path,
                geneval_report=after_report,
                metadata={"retry_budget_left": max_retry - retries_used},
            )
            episode.attempts.append(retry_attempt)
            current_attempt = retry_attempt
            if transition == "passed_after_retry":
                episode.final_outcome = "passed_after_retry"
                break

        if episode.final_outcome == "unknown":
            episode.final_outcome = "failed_after_budget"
        self.save_episode(episode)
        return episode

    def save_episode(self, episode: Episode) -> Path:
        path = self.output_dir / f"{episode.id}.json"
        write_json(path, episode.to_dict())
        return path

    def _state(
        self,
        episode: Episode,
        current_attempt: Attempt,
        retry_budget_left: int,
    ) -> dict[str, Any]:
        return {
            "episode_id": episode.id,
            "original_prompt": episode.original_prompt,
            "current_image_path": current_attempt.image_path,
            "geneval_report": current_attempt.geneval_report.to_dict(),
            "history_summary": _history_summary(episode),
            "retry_budget_left": retry_budget_left,
            "available_skills": available_skills(),
        }


def _history_summary(episode: Episode) -> str:
    parts: list[str] = []
    for attempt in episode.attempts:
        failed = [item.type for item in attempt.geneval_report.failed_constraints]
        parts.append(
            f"round={attempt.round} type={attempt.attempt_type} "
            f"score={attempt.geneval_report.score:.3f} failed={failed}"
        )
    return " | ".join(parts)

