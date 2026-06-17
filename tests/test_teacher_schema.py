from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.teacher.schemas import TeacherActionValidationError, validate_teacher_retry_action


class TeacherSchemaTest(unittest.TestCase):
    def test_valid_retry_action(self) -> None:
        action = validate_teacher_retry_action(
            {
                "decision": "retry",
                "failure_types": ["count_mismatch"],
                "skills_to_call": ["quantity_counting"],
                "preserve_constraints": ["Keep the apples red."],
                "repair_constraints": ["Render exactly three apples."],
                "repair_strategy": "Preserve colors and repair count.",
                "retry_prompt": "Exactly three red apples on a blue plate.",
                "expected_improvement": ["Counting should pass."],
                "regression_risks": ["Colors could regress."],
            }
        )
        self.assertEqual(action.decision, "retry")

    def test_rejects_extra_key(self) -> None:
        with self.assertRaises(TeacherActionValidationError):
            validate_teacher_retry_action(
                {
                    "decision": "submit",
                    "failure_types": [],
                    "skills_to_call": [],
                    "preserve_constraints": [],
                    "repair_constraints": [],
                    "repair_strategy": "Submit.",
                    "retry_prompt": "",
                    "expected_improvement": [],
                    "regression_risks": [],
                    "extra": "nope",
                }
            )

    def test_retry_requires_prompt(self) -> None:
        with self.assertRaises(TeacherActionValidationError):
            validate_teacher_retry_action(
                {
                    "decision": "retry",
                    "failure_types": ["count_mismatch"],
                    "skills_to_call": ["quantity_counting"],
                    "preserve_constraints": [],
                    "repair_constraints": ["Render exactly three apples."],
                    "repair_strategy": "Repair count.",
                    "retry_prompt": "",
                    "expected_improvement": [],
                    "regression_risks": [],
                }
            )


if __name__ == "__main__":
    unittest.main()
