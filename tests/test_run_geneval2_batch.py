from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_geneval2_batch import _jobs_from_manifest  # noqa: E402


class RunGeneval2BatchTest(unittest.TestCase):
    def test_manifest_candidate_index_filter_keeps_one_candidate_per_prompt(self) -> None:
        rows = []
        for prompt_index in range(3):
            for candidate_index in range(2):
                rows.append(
                    {
                        "candidate_id": f"prompt_{prompt_index}_cand_{candidate_index:02d}",
                        "candidate_index": candidate_index,
                        "sample_id": f"prompt_{prompt_index}",
                        "prompt": "plan-conditioned generation prompt",
                        "original_prompt": f"original prompt {prompt_index}",
                        "image_path": "/missing/image.png",
                        "metadata": {
                            "prompt_id": f"prompt_{prompt_index}",
                            "prompt": f"metadata original prompt {prompt_index}",
                            "source_index": prompt_index + 10,
                            "skills": ["count"],
                            "vqa_list": [["How many objects?", "one"]],
                        },
                    }
                )

        jobs, missing = _jobs_from_manifest(
            rows,
            limit=2,
            n_samples=2,
            candidate_index=0,
        )

        self.assertEqual(jobs, [])
        self.assertEqual(len(missing), 2)
        self.assertEqual([row["candidate_id"] for row in missing], ["prompt_0_cand_00", "prompt_1_cand_00"])
        self.assertEqual(missing[0]["prompt"], "original prompt 0")
        self.assertEqual(missing[0]["source_index"], 10)


if __name__ == "__main__":
    unittest.main()
