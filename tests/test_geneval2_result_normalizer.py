from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.evaluators.geneval2_result_normalizer import (
    load_geneval2_score_rows,
    normalize_geneval2_row,
    normalize_geneval2_score_list,
)
from gen_retry.evaluators.geneval2_adapter import Geneval2Adapter


class GenEval2ResultNormalizerTest(unittest.TestCase):
    def test_count_failure(self) -> None:
        report = normalize_geneval2_score_list(
            [
                {
                    "prompt_id": "p1",
                    "question": "Are there exactly three apples?",
                    "answer": "Yes",
                    "score": 0,
                    "skill": "count",
                }
            ]
        )["p1"]
        self.assertEqual(report.failed_constraints[0].type, "count_mismatch")
        self.assertIn("count_mismatch", report.critical_failure_types)

    def test_color_failure(self) -> None:
        constraint = normalize_geneval2_row(
            {
                "question": "Are the bicycles white?",
                "answer": "Yes",
                "score": 0,
                "skill": "attribute",
            }
        )
        self.assertEqual(constraint.type, "color_mismatch")
        self.assertEqual(constraint.status, "failed")

    def test_non_color_attribute_failure(self) -> None:
        constraint = normalize_geneval2_row(
            {
                "question": "Is the dog plastic?",
                "answer": "Yes",
                "score": 0,
                "skill": "attribute",
            }
        )
        self.assertEqual(constraint.type, "attribute_mismatch")

    def test_position_failure(self) -> None:
        constraint = normalize_geneval2_row(
            {
                "question": "Is the cube to the left of the sphere?",
                "answer": "Yes",
                "score": 0,
                "skill": "position",
            }
        )
        self.assertEqual(constraint.type, "spatial_mismatch")

    def test_object_pass(self) -> None:
        report = normalize_geneval2_score_list(
            [
                {
                    "prompt_id": "p1",
                    "question": "Is there a dog?",
                    "answer": "Yes",
                    "score": 1,
                    "skill": "object",
                }
            ]
        )["p1"]
        self.assertEqual(len(report.passed_constraints), 1)
        self.assertEqual(len(report.failed_constraints), 0)

    def test_aggregation(self) -> None:
        report = normalize_geneval2_score_list(
            [
                {
                    "prompt_id": "p1",
                    "question": "Is there a dog?",
                    "answer": "Yes",
                    "score": 1,
                    "skill": "object",
                },
                {
                    "prompt_id": "p1",
                    "question": "Are the bicycles white?",
                    "answer": "Yes",
                    "score": 0,
                    "skill": "attribute",
                },
                {
                    "prompt_id": "p1",
                    "question": "Is the cube to the left of the sphere?",
                    "answer": "Yes",
                    "score": 0.5,
                    "skill": "position",
                },
            ]
        )["p1"]
        self.assertAlmostEqual(report.score, 0.5)
        self.assertEqual(len(report.passed_constraints), 2)
        self.assertEqual(len(report.failed_constraints), 1)
        self.assertEqual(report.critical_failure_types, ["color_mismatch"])

    def test_atom_threshold_is_configurable(self) -> None:
        report = normalize_geneval2_score_list(
            [
                {
                    "prompt_id": "p1",
                    "question": "Is the cube to the left of the sphere?",
                    "answer": "Yes",
                    "score": 0.8,
                    "skill": "position",
                }
            ],
            atom_threshold=0.9,
        )["p1"]
        self.assertEqual(len(report.passed_constraints), 0)
        self.assertEqual(report.failed_constraints[0].type, "spatial_mismatch")
        self.assertEqual(report.raw_report["diagnostic_atom_threshold"], 0.9)

    def test_unparseable_score_is_uncertain(self) -> None:
        constraint = normalize_geneval2_row(
            {
                "question": "Are there any apples?",
                "answer": "Yes",
                "score": "not-a-number",
                "skill": "object",
            },
            atom_threshold=0.9,
        )
        self.assertEqual(constraint.status, "uncertain")

    def test_load_official_score_lists_with_benchmark_data(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            scores = root / "score_lists.json"
            bench = root / "geneval2_data.jsonl"
            scores.write_text(json.dumps([[0, 1]]), encoding="utf-8")
            bench.write_text(
                json.dumps(
                    {
                        "prompt": "three red apples",
                        "atom_count": 3,
                        "vqa_list": [
                            ["How many apples are in the image?", "three"],
                            ["Are there any apples in the image?", "Yes"],
                        ],
                        "skills": ["count", "object"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            rows = load_geneval2_score_rows(scores, benchmark_data=bench)
            self.assertEqual(rows[0]["question"], "How many apples are in the image?")
            report = normalize_geneval2_score_list(rows)["0"]
            self.assertEqual(report.failed_constraints[0].type, "count_mismatch")

    def test_official_score_lists_preserve_candidate_id_from_retry_benchmark(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            scores = root / "score_lists.json"
            bench = root / "eval_benchmark.jsonl"
            candidate_id = "geneval2_001_cand_00"
            scores.write_text(json.dumps([[0, 1]]), encoding="utf-8")
            bench.write_text(
                json.dumps(
                    {
                        "prompt": candidate_id,
                        "original_prompt": "two red apples on a table",
                        "prompt_id": "geneval2_001",
                        "candidate_id": candidate_id,
                        "candidate_index": 0,
                        "source_index": 123,
                        "vqa_list": [
                            ["How many apples are in the image?", "two"],
                            ["Are there apples in the image?", "Yes"],
                        ],
                        "skills": ["count", "object"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            rows = load_geneval2_score_rows(scores, benchmark_data=bench)
            reports = normalize_geneval2_score_list(rows, aggregate_by="candidate_id")

            self.assertEqual(rows[0]["candidate_id"], candidate_id)
            self.assertEqual(rows[0]["prompt_id"], "geneval2_001")
            self.assertEqual(rows[0]["prompt"], "two red apples on a table")
            self.assertEqual(rows[0]["eval_prompt"], candidate_id)
            self.assertEqual(set(reports), {candidate_id})
            self.assertEqual(reports[candidate_id].failed_constraints[0].type, "count_mismatch")

    def test_adapter_reads_score_list_path(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "image_path": "image_a.png",
                            "question": "Are the bicycles white?",
                            "answer": "Yes",
                            "score": 0,
                            "skill": "attribute",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            adapter = Geneval2Adapter(score_list_path=path, aggregate_by="image_path")
            report = adapter.evaluate("prompt", "image_a.png")
            self.assertEqual(report.failed_constraints[0].type, "color_mismatch")


if __name__ == "__main__":
    unittest.main()
