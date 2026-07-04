from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.quality.retry_plan_quality import check_retry_plan_package  # noqa: E402


class RetryPlanQualityTest(unittest.TestCase):
    def test_good_retry_package_has_no_critical_issues(self) -> None:
        package = _package()
        issues = check_retry_plan_package(package, package_path="memory.json")
        critical = [issue for issue in issues if issue.severity == "critical"]
        self.assertEqual(critical, [])

    def test_missing_failure_type_is_critical(self) -> None:
        package = _package()
        package["teacher_action"]["failure_types"] = []
        issues = check_retry_plan_package(package, package_path="memory.json")
        self.assertTrue(any(issue.code == "missing_failure_types" for issue in issues))


def _package() -> dict:
    return {
        "schema_version": "v1",
        "candidate_id": "cand_00",
        "stop": {"should_stop": False, "reason": "null"},
        "evaluation": {
            "score": 0.5,
            "passed_constraints": [
                {
                    "type": "color_mismatch",
                    "target": "apples",
                    "expected": "green",
                    "detected": "green",
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
        "teacher_request": {
            "candidate_id": "cand_00",
            "current_eval_report": {
                "score": 0.5,
                "passed_constraints": [
                    {
                        "type": "color_mismatch",
                        "target": "apples",
                        "expected": "green",
                        "detected": "green",
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
            "memory": {
                "regressed_constraints": [],
                "score_delta_from_previous": 0.0,
            },
        },
        "teacher_action": {
            "action_type": "retry_replan",
            "decision": "regenerate",
            "failure_types": ["count_mismatch"],
            "diagnosis": "The apples count is wrong.",
            "previous_plan_error": {
                "error_source": "prompt_specificity",
                "details": "The exact count was not enforced.",
            },
            "skill_revision": {
                "previous_skills": ["attribute_binding"],
                "new_skills": ["quantity_counting"],
                "reason": "The retry must repair the count.",
            },
            "preserve_constraints": ["Keep the apples green."],
            "repair_constraints": ["Render exactly 2 separate apples."],
            "regeneration_strategy": "Regenerate from scratch with exact count and green apples.",
            "retry_prompt": "A clear image of exactly 2 separate green apples on a plate.",
            "expected_improvement": ["The retry should fix the count."],
            "regression_risks": ["The green color could regress."],
            "branch_source_round": 0,
            "branch_source": "latest",
        },
    }


if __name__ == "__main__":
    unittest.main()
