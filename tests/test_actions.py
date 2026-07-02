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
            branch_source_round=1,
            branch_source="best_so_far",
        )
        action.validate()
        self.assertEqual(action.to_dict()["decision"], "regenerate")
        self.assertEqual(action.to_dict()["branch_source"], "best_so_far")

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

    def test_extra_action_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(ActionValidationError, "extra keys"):
            InitialPlanAction.from_dict(
                {
                    "action_type": "initial_plan",
                    "parsed_constraints": {"objects": [], "counts": {}, "attributes": {}, "relations": []},
                    "selected_skills": ["object_presence"],
                    "generation_strategy": "clear scene",
                    "initial_prompt": "a dog",
                    "generation_guards": [],
                    "notes": "not allowed",
                }
            )

    def test_bounding_box_retry_field_is_rejected(self) -> None:
        with self.assertRaises(ActionValidationError):
            RetryReplanAction.from_dict(
                {
                    "action_type": "retry_replan",
                    "decision": "regenerate",
                    "failure_types": ["spatial_mismatch"],
                    "diagnosis": "spatial_mismatch relation",
                    "previous_plan_error": {"error_source": "prompt", "details": ""},
                    "skill_revision": {
                        "previous_skills": ["spatial_layout"],
                        "new_skills": ["spatial_layout"],
                        "reason": "repair spatial relation",
                    },
                    "preserve_constraints": [],
                    "repair_constraints": ["spatial_mismatch relation"],
                    "regeneration_strategy": "regenerate",
                    "retry_prompt": "a dog left of a cat",
                    "expected_improvement": [],
                    "regression_risks": [],
                    "bounding_boxes": [],
                }
            )


if __name__ == "__main__":
    unittest.main()
