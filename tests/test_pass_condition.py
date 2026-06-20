from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.filters.filter_episodes import classify_transition, is_passed
from gen_retry.schemas.episode_schema import Constraint, NormalizedGenevalReport


class PassConditionTest(unittest.TestCase):
    def test_passes_when_no_failed_constraints(self) -> None:
        report = NormalizedGenevalReport(score=0.2, failed_constraints=[])
        self.assertTrue(is_passed(report))

    def test_passes_by_score_without_critical_failures(self) -> None:
        report = NormalizedGenevalReport(
            score=0.96,
            failed_constraints=[
                Constraint(type="low_visibility", target="bird", status="failed")
            ],
        )
        self.assertTrue(is_passed(report, pass_threshold=0.95))

    def test_does_not_pass_with_critical_failure(self) -> None:
        report = NormalizedGenevalReport(
            score=0.99,
            failed_constraints=[
                Constraint(type="count_mismatch", target="apple", status="failed")
            ],
        )
        self.assertFalse(is_passed(report, pass_threshold=0.95))

    def test_classifies_passed_after_retry(self) -> None:
        before = NormalizedGenevalReport(
            score=0.5,
            failed_constraints=[
                Constraint(type="color_mismatch", target="bird", status="failed")
            ],
        )
        after = NormalizedGenevalReport(score=1.0, failed_constraints=[])
        self.assertEqual(classify_transition(before, after), "passed_after_retry")


if __name__ == "__main__":
    unittest.main()
