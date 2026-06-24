from __future__ import annotations

import unittest
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.teachers.seed_teacher_adapter import SeedTeacherAdapter


class SeedTeacherAdapterTest(unittest.TestCase):
    def test_seed_adapter_uses_same_interface_without_hardcoded_key(self) -> None:
        adapter = SeedTeacherAdapter(base_url="https://example.invalid/v1", api_key="test-key")
        self.assertEqual(adapter.name, "seed_teacher_adapter")
        self.assertTrue(hasattr(adapter, "initial_plan"))
        self.assertTrue(hasattr(adapter, "retry_replan"))


if __name__ == "__main__":
    unittest.main()
