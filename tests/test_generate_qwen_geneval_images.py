from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_qwen_geneval_images import candidate_seed_from_metadata  # noqa: E402


class GenerateQwenGenevalImagesTest(unittest.TestCase):
    def test_uses_metadata_seed_when_present(self) -> None:
        self.assertEqual(
            candidate_seed_from_metadata(
                {"seed": 1320},
                base_seed=3000,
                prompt_index=17,
                n_samples=1,
                candidate_index=0,
            ),
            1320,
        )

    def test_offsets_metadata_seed_for_multiple_samples(self) -> None:
        self.assertEqual(
            candidate_seed_from_metadata(
                {"seed": "1320"},
                base_seed=3000,
                prompt_index=17,
                n_samples=3,
                candidate_index=2,
            ),
            1322,
        )

    def test_falls_back_to_computed_seed_without_metadata_seed(self) -> None:
        self.assertEqual(
            candidate_seed_from_metadata(
                {},
                base_seed=3000,
                prompt_index=17,
                n_samples=3,
                candidate_index=2,
            ),
            3053,
        )


if __name__ == "__main__":
    unittest.main()
