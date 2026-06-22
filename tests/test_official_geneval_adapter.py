from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.evaluators.official_geneval_adapter import official_result_to_candidate_row
from gen_retry.filters.geneval_selection import select_teacher_candidates, teacher_rows_from_selected


class OfficialGenevalAdapterTest(unittest.TestCase):
    def test_converts_official_counting_failure_to_teacher_row(self) -> None:
        metadata = {
            "tag": "counting",
            "include": [{"class": "apple", "count": 3}],
            "prompt": "a photo of three apples",
        }
        row = {
            "filename": "/tmp/geneval_images/00000/samples/00000.png",
            "tag": "counting",
            "prompt": "a photo of three apples",
            "correct": False,
            "reason": "expected apple>=3, found 2",
            "metadata": json.dumps(metadata),
            "details": json.dumps({"apple": [[0, 0, 10, 10, 0.95], [20, 0, 30, 10, 0.91]]}),
        }
        candidate = official_result_to_candidate_row(row)
        diagnostic = candidate["diagnostic"]
        self.assertEqual(candidate["sample_id"], "00000")
        self.assertEqual(candidate["candidate_id"], "00000_cand_00")
        self.assertEqual(diagnostic["checks"]["counting"], False)
        self.assertIn("count_mismatch", diagnostic["critical_failure_types"])
        teacher_row = candidate["teacher_row"]
        self.assertEqual(teacher_row["id"], "00000_cand_00")
        self.assertEqual(teacher_row["diagnostic"]["expected"]["count"]["apple"], 3)

    def test_multi_word_object_is_not_misread_as_color_failure(self) -> None:
        metadata = {
            "tag": "single_object",
            "include": [{"class": "traffic light", "count": 1}],
            "prompt": "a photo of a traffic light",
        }
        row = {
            "filename": "/tmp/geneval_images/00001/samples/00000.png",
            "tag": "single_object",
            "prompt": "a photo of a traffic light",
            "correct": False,
            "reason": "expected traffic light>=1, found 0",
            "metadata": json.dumps(metadata),
            "details": json.dumps({}),
        }
        candidate = official_result_to_candidate_row(row)
        checks = candidate["diagnostic"]["checks"]
        self.assertEqual(checks["object_presence"], False)
        self.assertNotIn("color_binding", checks)

    def test_selects_failed_candidates_from_mid_score_prompt(self) -> None:
        candidates = []
        for sample_id, scores in {"a": [1.0, 0.0, 0.0, 1.0], "b": [1.0, 1.0, 1.0, 1.0]}.items():
            for index, score in enumerate(scores):
                candidates.append(
                    {
                        "sample_id": sample_id,
                        "candidate_id": f"{sample_id}_cand_{index:02d}",
                        "prompt": f"prompt {sample_id}",
                        "geneval_report": {"score": score},
                        "diagnostic": {"failed_constraints": [] if score == 1.0 else [{"type": "x"}]},
                        "teacher_row": {"id": f"{sample_id}_cand_{index:02d}"},
                    }
                )
        selected, prompt_rows = select_teacher_candidates(
            candidates,
            min_score=0.25,
            max_score=0.75,
            candidate_policy="failed",
        )
        teacher_rows = teacher_rows_from_selected(selected)
        self.assertEqual([row["sample_id"] for row in prompt_rows if row["selected"]], ["a"])
        self.assertEqual([row["id"] for row in teacher_rows], ["a_cand_01", "a_cand_02"])
        self.assertEqual(teacher_rows[0]["selection_metadata"]["prompt_score"], 0.5)


if __name__ == "__main__":
    unittest.main()
