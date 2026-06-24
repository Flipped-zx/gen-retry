from __future__ import annotations

import unittest
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.evaluators.normalizer import normalize_geneval2_report, normalize_geneval_report


class NormalizerTest(unittest.TestCase):
    def test_geneval_report_maps_critical_failure(self) -> None:
        report = normalize_geneval_report(
            {
                "score": 0.5,
                "failed_constraints": [
                    {"type": "count_mismatch", "target": "apple", "expected": 3, "detected": 2}
                ],
            }
        )
        self.assertEqual(report.critical_failure_types, ["count_mismatch"])

    def test_geneval2_atoms_map_to_failed_constraints(self) -> None:
        report = normalize_geneval2_report(
            {
                "atoms": [
                    {
                        "type": "relation_mismatch",
                        "target": "cube left_of sphere",
                        "passed": False,
                        "expected": "left",
                        "detected": "right",
                    }
                ]
            }
        )
        self.assertEqual(report.failed_constraints[0].type, "relation_mismatch")
        self.assertEqual(report.critical_failure_types, ["relation_mismatch"])


if __name__ == "__main__":
    unittest.main()
