from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.teachers.gpt55_teacher_adapter import GPT55TeacherAdapter  # noqa: E402


class GPT55TeacherAdapterTest(unittest.TestCase):
    def test_retry_replan_repairs_schema_valid_but_low_quality_action(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmp:
            teacher = _FakeGPTTeacher(
                [_bad_action(), _good_action()],
                log_dir=tmp,
                max_parse_retries=1,
            )

            action = teacher.retry_replan(_state())

            self.assertEqual(action.failure_types, ["count_mismatch"])
            self.assertIn("quantity_counting", action.skill_revision["new_skills"])
            self.assertTrue(action.preserve_constraints)
            self.assertEqual(len(teacher.calls), 2)
            self.assertIn("quality checks", teacher.calls[1][-1]["content"])

    def test_retry_replan_raises_when_quality_repair_is_exhausted(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmp:
            teacher = _FakeGPTTeacher(
                [_bad_action()],
                log_dir=tmp,
                max_parse_retries=0,
            )

            with self.assertRaises(ValueError) as ctx:
                teacher.retry_replan(_state())
            self.assertIn("missing_failure_types", str(ctx.exception))


class _FakeGPTTeacher(GPT55TeacherAdapter):
    def __init__(self, actions: list[dict], **kwargs) -> None:
        super().__init__(base_url="https://teacher.invalid/v1", api_key="test-key", **kwargs)
        self.actions = list(actions)
        self.calls: list[list[dict[str, str]]] = []

    def _post_chat(self, messages: list[dict[str, str]]) -> dict:
        self.calls.append([dict(message) for message in messages])
        if not self.actions:
            raise RuntimeError("no fake response left")
        content = json.dumps(self.actions.pop(0))
        return {"choices": [{"message": {"content": content}}]}

    def _log_raw_response(self, call_type: str, response: dict) -> None:
        _ = call_type, response


def _state() -> dict:
    return {
        "original_prompt": "two red apples on a table",
        "previous_initial_plan": {
            "action_type": "initial_plan",
            "parsed_constraints": {
                "objects": ["apples"],
                "counts": {"apples": 2},
                "attributes": {"apples": "red"},
                "relations": [],
            },
            "selected_skills": ["quantity_counting", "attribute_binding"],
            "generation_strategy": "Make the apples countable and red.",
            "initial_prompt": "A clear image of exactly two red apples on a table.",
            "generation_guards": ["No extra apples."],
        },
        "previous_action": {},
        "previous_prompt": "A clear image of exactly two red apples on a table.",
        "previous_selected_skills": ["quantity_counting", "attribute_binding"],
        "normalized_eval_report": {
            "score": 0.5,
            "passed_constraints": [
                {
                    "type": "color_mismatch",
                    "target": "apples",
                    "expected": "red",
                    "detected": "red",
                    "status": "passed",
                }
            ],
            "failed_constraints": [
                {
                    "type": "count_mismatch",
                    "target": "apples",
                    "expected": 2,
                    "detected": 1,
                    "status": "failed",
                }
            ],
            "uncertain_constraints": [],
            "critical_failure_types": ["count_mismatch"],
        },
        "retry_history": [],
        "retry_budget_left": 3,
        "current_round": 0,
        "best_so_far": {"round": 0, "score": 0.5, "prompt": "prompt", "failed_constraints": []},
        "fixed_constraints": [],
        "persistent_failures": [],
        "new_failures": [],
        "regressed_constraints": [],
        "score_delta_from_previous": 0.0,
        "score_delta_from_best": 0.0,
        "branch_source": "latest",
        "branch_source_round": 0,
    }


def _bad_action() -> dict:
    action = _good_action()
    action["failure_types"] = []
    action["skill_revision"] = {
        "previous_skills": [],
        "new_skills": [],
        "reason": "Retry.",
    }
    action["preserve_constraints"] = []
    return action


def _good_action() -> dict:
    return {
        "action_type": "retry_replan",
        "decision": "regenerate",
        "failure_types": ["count_mismatch"],
        "diagnosis": "The image has one apple but the prompt requires exactly two apples.",
        "previous_plan_error": {
            "error_source": "prompt_specificity",
            "details": "The count was not emphasized enough.",
        },
        "skill_revision": {
            "previous_skills": ["attribute_binding"],
            "new_skills": ["quantity_counting"],
            "reason": "The retry must enforce exact count.",
        },
        "preserve_constraints": ["Keep the apples red."],
        "repair_constraints": ["Show exactly two separate red apples."],
        "regeneration_strategy": "Regenerate with two separate visible apples and no extras.",
        "retry_prompt": "A clear image of exactly two separate red apples on a table, no extra apples.",
        "expected_improvement": ["The count should be corrected to two apples."],
        "regression_risks": ["The red color could regress."],
        "branch_source_round": 0,
        "branch_source": "latest",
    }


if __name__ == "__main__":
    unittest.main()
