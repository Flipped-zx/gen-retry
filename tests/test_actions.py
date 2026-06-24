from __future__ import annotations

import unittest
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.schemas.actions import ActionValidationError, InitialPlanAction, RetryReplanAction


class PlannerActionSchemaTest(unittest.TestCase):
    def test_initial_plan_validates_allowed_skills(self) -> None:
        action = InitialPlanAction(
            parsed_constraints={"objects": ["apple"], "counts": {"apple": 3}, "attributes": {}, "relations": []},
            selected_skills=["quantity_counting", "attribute_binding"],
            generation_strategy="count clearly",
            initial_prompt="three red apples",
        )
        action.validate()

    def test_invalid_skill_is_rejected(self) -> None:
        with self.assertRaises(ActionValidationError):
            InitialPlanAction(
                selected_skills=["unknown_skill"],
                initial_prompt="a dog",
            ).validate()

    def test_retry_replan_requires_retry_prompt_and_regenerate(self) -> None:
        action = RetryReplanAction(
            failure_types=["missing_object"],
            diagnosis="missing_object dog",
            skill_revision={"previous_skills": [], "new_skills": ["object_presence"], "reason": "missing dog"},
            repair_constraints=["missing_object dog must be visible"],
            retry_prompt="a visible dog",
        )
        action.validate()
        self.assertEqual(action.to_dict()["decision"], "regenerate")

    def test_direct_image_edit_action_is_rejected(self) -> None:
        with self.assertRaises(ActionValidationError):
            RetryReplanAction.from_dict(
                {
                    "action_type": "retry_replan",
                    "decision": "regenerate",
                    "failure_types": ["missing_object"],
                    "diagnosis": "missing_object dog",
                    "skill_revision": {"previous_skills": [], "new_skills": ["object_presence"], "reason": ""},
                    "repair_constraints": ["missing_object dog"],
                    "retry_prompt": "a dog",
                    "edit_instruction": "add dog",
                }
            )


if __name__ == "__main__":
    unittest.main()
