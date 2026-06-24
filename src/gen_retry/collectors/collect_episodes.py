"""Production episode collector for regeneration-only retry trajectories."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

from gen_retry.evaluators.base import BaseImageEvaluator
from gen_retry.generators.base import BaseGenerator
from gen_retry.schemas.actions import ActionValidationError, InitialPlanAction, RetryReplanAction
from gen_retry.schemas.episode import Attempt, Episode, StopRuleResult
from gen_retry.schemas.reports import NormalizedEvalReport
from gen_retry.teachers.base import BaseTeacher
from gen_retry.utils.ids import make_episode_id
from gen_retry.utils.io import append_jsonl, write_json


def is_passed(report: NormalizedEvalReport, pass_threshold: float = 0.95) -> bool:
    if not report.failed_constraints:
        return True
    if report.score >= pass_threshold and not report.critical_failure_types:
        return True
    return False


def should_continue(
    report: NormalizedEvalReport,
    retry_round: int,
    max_retry: int,
    pass_threshold: float = 0.95,
) -> StopRuleResult:
    passed = is_passed(report, pass_threshold=pass_threshold)
    if not report.failed_constraints:
        return StopRuleResult(
            should_stop=True,
            reason="no_failed_constraints",
            passed=True,
            retry_round=retry_round,
            max_retry=max_retry,
            pass_threshold=pass_threshold,
            score=report.score,
            critical_failure_types=list(report.critical_failure_types),
        )
    if passed:
        return StopRuleResult(
            should_stop=True,
            reason="score_threshold_without_critical_failure",
            passed=True,
            retry_round=retry_round,
            max_retry=max_retry,
            pass_threshold=pass_threshold,
            score=report.score,
            critical_failure_types=list(report.critical_failure_types),
        )
    if retry_round >= max_retry:
        return StopRuleResult(
            should_stop=True,
            reason="retry_budget_exhausted",
            passed=False,
            retry_round=retry_round,
            max_retry=max_retry,
            pass_threshold=pass_threshold,
            score=report.score,
            critical_failure_types=list(report.critical_failure_types),
        )
    return StopRuleResult(
        should_stop=False,
        reason="continue_retry",
        passed=False,
        retry_round=retry_round,
        max_retry=max_retry,
        pass_threshold=pass_threshold,
        score=report.score,
        critical_failure_types=list(report.critical_failure_types),
    )


class EpisodeCollector:
    def __init__(
        self,
        *,
        teacher: BaseTeacher,
        generator: BaseGenerator,
        evaluator: BaseImageEvaluator,
        output_dir: str | Path = "data/raw_episodes",
        image_dir: str | Path = "data/images",
        error_path: str | Path = "data/failed/collector_errors.jsonl",
        resume: bool = False,
    ) -> None:
        self.teacher = teacher
        self.generator = generator
        self.evaluator = evaluator
        self.output_dir = Path(output_dir)
        self.image_dir = Path(image_dir)
        self.error_path = Path(error_path)
        self.resume = resume

    def run_episode(
        self,
        prompt: str,
        evaluator_type: str = "geneval",
        max_retry: int = 2,
        pass_threshold: float = 0.95,
        episode_id: str | None = None,
        prompt_metadata: dict[str, Any] | None = None,
    ) -> Episode:
        episode_id = episode_id or make_episode_id(prompt)
        output_path = self.output_dir / f"{episode_id}.json"
        if self.resume and output_path.exists():
            return Episode.from_dict(_read_episode(output_path))

        try:
            return self._run_episode(
                prompt=prompt,
                evaluator_type=evaluator_type,
                max_retry=max_retry,
                pass_threshold=pass_threshold,
                episode_id=episode_id,
                prompt_metadata=prompt_metadata or {},
            )
        except ActionValidationError:
            raise
        except Exception as exc:
            self._record_error(episode_id=episode_id, prompt=prompt, error=exc)
            raise

    def _run_episode(
        self,
        *,
        prompt: str,
        evaluator_type: str,
        max_retry: int,
        pass_threshold: float,
        episode_id: str,
        prompt_metadata: dict[str, Any],
    ) -> Episode:
        initial_plan = self.teacher.initial_plan(
            original_prompt=prompt,
            evaluator_type=evaluator_type,
            prompt_metadata=prompt_metadata,
        )
        image_path = self.generator.generate(
            initial_plan.initial_prompt,
            str(self._image_path(episode_id, 0)),
            {"episode_id": episode_id, "round": 0, "action_type": "initial_plan"},
        )
        report = self.evaluator.evaluate(prompt, image_path)
        initial_attempt = Attempt(
            round=0,
            prompt_used=initial_plan.initial_prompt,
            image_path=image_path,
            eval_report=report,
            planner_action=initial_plan,
            metadata={"retry_budget_left": max_retry, "transition_outcome": "initial"},
        )
        episode = Episode(
            episode_id=episode_id,
            original_prompt=prompt,
            evaluator_type=evaluator_type,
            generator_name=getattr(self.generator, "name", self.generator.__class__.__name__),
            teacher_name=getattr(self.teacher, "name", self.teacher.__class__.__name__),
            initial_plan=initial_plan,
            attempts=[initial_attempt],
            metadata={
                "max_retry": max_retry,
                "pass_threshold": pass_threshold,
                "prompt_metadata": prompt_metadata,
            },
        )
        stop = should_continue(report, 0, max_retry, pass_threshold)
        episode.stop_rule_result = stop
        if stop.should_stop and stop.passed:
            episode.final_outcome = "pass_without_retry"
            self.save_episode(episode)
            return episode

        previous_report = report
        best_score = report.score
        any_improved = False
        regressed = False
        for retry_round in range(1, max_retry + 1):
            state = self._retry_state(
                episode=episode,
                previous_attempt=episode.attempts[-1],
                retry_round=retry_round,
                retry_budget_left=max_retry - retry_round + 1,
            )
            action = self.teacher.retry_replan(state)
            retry_image_path = self.generator.generate(
                action.retry_prompt,
                str(self._image_path(episode_id, retry_round)),
                {"episode_id": episode_id, "round": retry_round, "action_type": "retry_replan"},
            )
            after_report = self.evaluator.evaluate(prompt, retry_image_path)
            transition = classify_transition(previous_report, after_report, pass_threshold)
            any_improved = any_improved or transition in {"passed_after_retry", "improved_after_retry"}
            regressed = regressed or transition == "regressed"
            attempt = Attempt(
                round=retry_round,
                prompt_used=action.retry_prompt,
                image_path=retry_image_path,
                eval_report=after_report,
                planner_action=action,
                metadata={
                    "retry_budget_left": max_retry - retry_round,
                    "transition_outcome": transition,
                    "previous_score": previous_report.score,
                    "score_delta": after_report.score - previous_report.score,
                    "failed_constraints_delta": len(after_report.failed_constraints)
                    - len(previous_report.failed_constraints),
                    "new_critical_failures": _new_critical_failures(previous_report, after_report),
                },
            )
            episode.attempts.append(attempt)
            best_score = max(best_score, after_report.score)
            stop = should_continue(after_report, retry_round, max_retry, pass_threshold)
            episode.stop_rule_result = stop
            previous_report = after_report
            if stop.should_stop:
                break

        final_report = episode.attempts[-1].eval_report
        if is_passed(final_report, pass_threshold):
            episode.final_outcome = "passed_after_retry"
        elif regressed and final_report.score < best_score:
            episode.final_outcome = "regressed"
        elif any_improved:
            episode.final_outcome = "improved_after_retry"
        else:
            episode.final_outcome = "failed_after_budget"
        self.save_episode(episode)
        return episode

    def save_episode(self, episode: Episode) -> Path:
        path = self.output_dir / f"{episode.episode_id}.json"
        write_json(path, episode.to_dict())
        return path

    def _retry_state(
        self,
        *,
        episode: Episode,
        previous_attempt: Attempt,
        retry_round: int,
        retry_budget_left: int,
    ) -> dict[str, Any]:
        return {
            "episode_id": episode.episode_id,
            "original_prompt": episode.original_prompt,
            "previous_initial_plan": episode.initial_plan.to_dict(),
            "previous_prompt": previous_attempt.prompt_used,
            "previous_selected_skills": _previous_skills(previous_attempt, episode.initial_plan),
            "normalized_eval_report": previous_attempt.eval_report.to_dict(),
            "retry_history": _retry_history(episode),
            "retry_round": retry_round,
            "retry_budget_left": retry_budget_left,
            "evaluator_type": episode.evaluator_type,
        }

    def _image_path(self, episode_id: str, round_id: int) -> Path:
        return self.image_dir / f"{episode_id}_attempt_{round_id}.png"

    def _record_error(self, *, episode_id: str, prompt: str, error: Exception) -> None:
        append_jsonl(
            self.error_path,
            [
                {
                    "episode_id": episode_id,
                    "prompt": prompt,
                    "error_type": error.__class__.__name__,
                    "error": str(error),
                    "traceback": traceback.format_exc(limit=6),
                }
            ],
        )


def run_episode(
    prompt: str,
    evaluator_type: str,
    teacher: BaseTeacher,
    generator: BaseGenerator,
    evaluator: BaseImageEvaluator,
    max_retry: int = 2,
    pass_threshold: float = 0.95,
) -> Episode:
    collector = EpisodeCollector(teacher=teacher, generator=generator, evaluator=evaluator)
    return collector.run_episode(
        prompt,
        evaluator_type=evaluator_type,
        max_retry=max_retry,
        pass_threshold=pass_threshold,
    )


def classify_transition(
    before_report: NormalizedEvalReport,
    after_report: NormalizedEvalReport,
    pass_threshold: float = 0.95,
) -> str:
    if is_passed(after_report, pass_threshold):
        return "passed_after_retry"
    before_failed = len(before_report.failed_constraints)
    after_failed = len(after_report.failed_constraints)
    new_critical = _new_critical_failures(before_report, after_report)
    if new_critical or after_failed > before_failed or after_report.score < before_report.score:
        return "regressed"
    if after_failed < before_failed or after_report.score > before_report.score:
        return "improved_after_retry"
    return "no_improvement"


def _retry_history(episode: Episode) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for attempt in episode.attempts:
        action = attempt.planner_action
        rows.append(
            {
                "round": attempt.round,
                "prompt_used": attempt.prompt_used,
                "score": attempt.eval_report.score,
                "failed_constraints": [
                    item.to_dict() for item in attempt.eval_report.failed_constraints
                ],
                "planner_action_type": action.action_type if action else "",
                "transition_outcome": attempt.metadata.get("transition_outcome"),
            }
        )
    return rows


def _previous_skills(previous_attempt: Attempt, initial_plan: InitialPlanAction) -> list[str]:
    action = previous_attempt.planner_action
    if isinstance(action, RetryReplanAction):
        return [
            str(item)
            for item in action.skill_revision.get("new_skills", [])
            if str(item).strip()
        ]
    return list(initial_plan.selected_skills)


def _new_critical_failures(before_report: NormalizedEvalReport, after_report: NormalizedEvalReport) -> list[str]:
    return sorted(set(after_report.critical_failure_types) - set(before_report.critical_failure_types))


def _read_episode(path: Path) -> dict[str, Any]:
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data
