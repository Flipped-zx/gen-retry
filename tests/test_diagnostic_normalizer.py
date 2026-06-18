from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.eval.diagnostic_normalizer import normalize_geneval_diagnostic


class DiagnosticNormalizerTest(unittest.TestCase):
    def test_counting_failure_preserves_color(self) -> None:
        diagnostic = json.loads(
            (ROOT / "examples" / "geneval_diagnostic_example.json").read_text(encoding="utf-8")
        )
        normalized = normalize_geneval_diagnostic(diagnostic)
        self.assertIn("count_mismatch", normalized["failure_types"])
        self.assertEqual(normalized["repair_targets"][0]["skill"], "quantity_counting")
        self.assertIn(
            {"target": "apple", "property": "color", "value": "red"},
            normalized["preserve_candidates"],
        )
        self.assertIn(
            {"target": "plate", "property": "color", "value": "blue"},
            normalized["preserve_candidates"],
        )

    def test_visibility_failure_routes_to_anti_occlusion_skill(self) -> None:
        normalized = normalize_geneval_diagnostic(
            {
                "prompt": "a red backpack visible behind a chair",
                "category": "visibility_occlusion",
                "expected": {
                    "objects": ["backpack", "chair"],
                    "count": {"backpack": 1, "chair": 1},
                    "color": {"backpack": "red"},
                },
                "detected": [
                    {"label": "backpack", "score": 0.41, "color": "red"},
                    {"label": "chair", "score": 0.89},
                ],
                "checks": {
                    "object_presence": True,
                    "counting": True,
                    "color_binding": True,
                    "low_visibility": False,
                },
                "failure_reason": "backpack is present but too occluded for reliable judging",
            }
        )
        self.assertIn("low_visibility", normalized["failure_types"])
        self.assertIn(
            {
                "failure_type": "low_visibility",
                "instruction": "Make the required objects visible enough for judging: backpack is present but too occluded for reliable judging.",
                "skill": "visibility_and_anti_occlusion",
                "target": "required visible constraints",
            },
            normalized["repair_targets"],
        )


if __name__ == "__main__":
    unittest.main()
