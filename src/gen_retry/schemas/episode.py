"""Episode schemas for Geneval/Geneval2-guided regeneration trajectories."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gen_retry.schemas.actions import InitialPlanAction, RetryReplanAction, parse_action
from gen_retry.schemas.reports import NormalizedEvalReport


EVALUATOR_TYPES = {"geneval", "geneval2"}
FINAL_OUTCOMES = {
    "pass_without_retry",
    "passed_after_retry",
    "improved_after_retry",
    "failed_after_budget",
    "regressed",
    "invalid_teacher_action",
    "generator_error",
    "evaluator_error",
}


@dataclass
class StopRuleResult:
    should_stop: bool
    reason: str
    passed: bool
    retry_round: int
    max_retry: int
    pass_threshold: float = 0.95
    score: float = 0.0
    critical_failure_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_stop": self.should_stop,
            "reason": self.reason,
            "passed": self.passed,
            "retry_round": self.retry_round,
            "max_retry": self.max_retry,
            "pass_threshold": self.pass_threshold,
            "score": self.score,
            "critical_failure_types": list(self.critical_failure_types),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StopRuleResult":
        return cls(
            should_stop=bool(data.get("should_stop", False)),
            reason=str(data.get("reason", "")),
            passed=bool(data.get("passed", False)),
            retry_round=int(data.get("retry_round", 0)),
            max_retry=int(data.get("max_retry", 0)),
            pass_threshold=float(data.get("pass_threshold", 0.95)),
            score=float(data.get("score", 0.0)),
            critical_failure_types=[
                str(item) for item in data.get("critical_failure_types", []) if str(item).strip()
            ],
        )


@dataclass
class Attempt:
    round: int
    prompt_used: str
    image_path: str
    eval_report: NormalizedEvalReport
    planner_action: InitialPlanAction | RetryReplanAction | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "prompt_used": self.prompt_used,
            "image_path": self.image_path,
            "eval_report": self.eval_report.to_dict(),
            "planner_action": self.planner_action.to_dict() if self.planner_action else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Attempt":
        action_data = data.get("planner_action")
        return cls(
            round=int(data.get("round", 0)),
            prompt_used=str(data.get("prompt_used", "")),
            image_path=str(data.get("image_path", "")),
            eval_report=NormalizedEvalReport.from_dict(dict(data.get("eval_report") or {})),
            planner_action=parse_action(action_data) if isinstance(action_data, dict) else None,
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class Episode:
    episode_id: str
    original_prompt: str
    evaluator_type: str
    generator_name: str
    teacher_name: str
    initial_plan: InitialPlanAction
    attempts: list[Attempt] = field(default_factory=list)
    stop_rule_result: StopRuleResult | None = None
    final_outcome: str = "failed_after_budget"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "original_prompt": self.original_prompt,
            "evaluator_type": self.evaluator_type,
            "generator_name": self.generator_name,
            "teacher_name": self.teacher_name,
            "initial_plan": self.initial_plan.to_dict(),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "stop_rule_result": self.stop_rule_result.to_dict() if self.stop_rule_result else {},
            "final_outcome": self.final_outcome,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Episode":
        stop = data.get("stop_rule_result")
        return cls(
            episode_id=str(data.get("episode_id", data.get("id", ""))),
            original_prompt=str(data.get("original_prompt", "")),
            evaluator_type=str(data.get("evaluator_type", "geneval")),
            generator_name=str(data.get("generator_name", "")),
            teacher_name=str(data.get("teacher_name", "")),
            initial_plan=InitialPlanAction.from_dict(dict(data.get("initial_plan") or {})),
            attempts=[
                Attempt.from_dict(item)
                for item in data.get("attempts", [])
                if isinstance(item, dict)
            ],
            stop_rule_result=StopRuleResult.from_dict(stop) if isinstance(stop, dict) and stop else None,
            final_outcome=str(data.get("final_outcome", "")),
            metadata=dict(data.get("metadata") or {}),
        )
