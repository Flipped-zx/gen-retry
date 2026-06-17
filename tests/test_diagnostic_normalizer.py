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


if __name__ == "__main__":
    unittest.main()
