from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.data.validate_trajectory import validate_trajectory_object


class TrajectorySchemaTest(unittest.TestCase):
    def test_example_trajectory_is_valid(self) -> None:
        example = json.loads(
            (ROOT / "examples" / "geneval_retry_example.json").read_text(encoding="utf-8")
        )
        self.assertEqual(validate_trajectory_object(example), [])

    def test_missing_steps_is_invalid(self) -> None:
        self.assertIn(
            "missing top-level fields: diagnostic_input, normalized_diagnostic, outcome, source_prompt, steps, trajectory_id",
            validate_trajectory_object({"schema_version": "0.1"}),
        )


if __name__ == "__main__":
    unittest.main()
