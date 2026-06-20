from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.schemas.episode_schema import Constraint, NormalizedGenevalReport
from gen_retry.teachers.mock_teacher import MockTeacher


class MockTeacherTest(unittest.TestCase):
    def test_submit_when_no_failed_constraints(self) -> None:
        action = MockTeacher().act(
            {
                "original_prompt": "a red apple",
                "geneval_report": NormalizedGenevalReport(score=1.0).to_dict(),
            }
        )
        self.assertEqual(action.decision, "submit")
        self.assertEqual(action.action_type, "submit")

    def test_retry_when_failed_constraints_exist(self) -> None:
        report = NormalizedGenevalReport(
            score=0.5,
            failed_constraints=[
                Constraint(type="missing_object", target="dog", expected="visible", detected="missing")
            ],
        )
        action = MockTeacher().act(
            {
                "original_prompt": "a dog under a table",
                "geneval_report": report.to_dict(),
            }
        )
        self.assertEqual(action.decision, "retry")
        self.assertEqual(action.skill, "object_presence")
        self.assertTrue(action.edit_instruction)


if __name__ == "__main__":
    unittest.main()
