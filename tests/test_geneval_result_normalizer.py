from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.evaluators.geneval_result_normalizer import normalize_geneval_output


class GenevalResultNormalizerTest(unittest.TestCase):
    def test_normalizes_check_style_count_failure(self) -> None:
        normalized, diagnostic = normalize_geneval_output(
            {
                "expected": {
                    "objects": ["apple", "plate"],
                    "count": {"apple": 3, "plate": 1},
                    "color": {"apple": "red", "plate": "blue"},
                },
                "detected": [
                    {"label": "apple", "color": "red"},
                    {"label": "apple", "color": "red"},
                    {"label": "plate", "color": "blue"},
                ],
                "checks": {
                    "object_presence": True,
                    "counting": False,
                    "color_binding": True,
                },
            },
            prompt="three red apples on a blue plate",
            category="counting_color",
        )
        self.assertEqual(normalized.failed_constraints[0].type, "count_mismatch")
        self.assertEqual(normalized.failed_constraints[0].target, "apple")
        self.assertIn("count_mismatch", diagnostic["critical_failure_types"])
        self.assertIn("expected 3", diagnostic["failure_reason"])

    def test_normalizes_structured_constraints(self) -> None:
        normalized, diagnostic = normalize_geneval_output(
            {
                "score": 0.4,
                "failed_constraints": [
                    {
                        "type": "spatial_mismatch",
                        "target": "cube left_of sphere",
                        "expected": "left_of",
                        "detected": "right_of",
                    }
                ],
            },
            prompt="a green cube to the left of a yellow sphere",
        )
        self.assertEqual(normalized.score, 0.4)
        self.assertEqual(diagnostic["checks"]["spatial_relation"], False)


if __name__ == "__main__":
    unittest.main()

