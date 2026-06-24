from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.collectors.collect_episodes import EpisodeCollector
from gen_retry.evaluators.mock_geneval import MockGenevalEvaluator
from gen_retry.export.export_sft import export_episode_sft
from gen_retry.generators.mock_generator import MockGenerator
from gen_retry.teachers.mock_teacher import MockTeacher


class ExportSftTest(unittest.TestCase):
    def test_export_creates_initial_and_retry_sharegpt_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = [
                {
                    "prompt": "two blue birds",
                    "mock_reports": [
                        {
                            "score": 0.4,
                            "failed_constraints": [
                                {"type": "color_mismatch", "target": "bird", "expected": "blue", "detected": "green"}
                            ],
                        },
                        {"score": 1.0, "failed_constraints": []},
                    ],
                }
            ]
            collector = EpisodeCollector(
                teacher=MockTeacher(),
                generator=MockGenerator(),
                evaluator=MockGenevalEvaluator(records),
                output_dir=root / "episodes",
                image_dir=root / "images",
            )
            collector.run_episode("two blue birds", episode_id="episode_export")
            output = root / "sft.jsonl"
            rejected = root / "rejected.jsonl"
            count = export_episode_sft(root / "episodes", output, rejected_output=rejected)
            self.assertEqual(count, 2)
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual({row["metadata"]["sample_type"] for row in rows}, {"initial_plan", "retry_replan"})
            for row in rows:
                self.assertEqual([message["role"] for message in row["messages"]], ["system", "user", "assistant"])
                self.assertNotIn("image_path", row["messages"][1]["content"])
                self.assertNotIn("raw_report", row["messages"][1]["content"])
            retry_target = json.loads(rows[1]["messages"][2]["content"])
            self.assertEqual(retry_target["decision"], "regenerate")
            self.assertTrue(retry_target["retry_prompt"])

    def test_export_writes_rejected_retry_samples(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = [
                {
                    "prompt": "a visible dog",
                    "mock_reports": [
                        {
                            "score": 0.4,
                            "failed_constraints": [
                                {"type": "missing_object", "target": "dog", "expected": "present", "detected": "missing"}
                            ],
                        },
                        {
                            "score": 0.4,
                            "failed_constraints": [
                                {"type": "missing_object", "target": "dog", "expected": "present", "detected": "missing"}
                            ],
                        },
                    ],
                }
            ]
            collector = EpisodeCollector(
                teacher=MockTeacher(),
                generator=MockGenerator(),
                evaluator=MockGenevalEvaluator(records),
                output_dir=root / "episodes",
                image_dir=root / "images",
            )
            collector.run_episode("a visible dog", max_retry=1, episode_id="episode_reject")
            output = root / "sft.jsonl"
            rejected = root / "rejected.jsonl"
            count = export_episode_sft(root / "episodes", output, rejected_output=rejected)
            self.assertEqual(count, 1)
            rejected_rows = [json.loads(line) for line in rejected.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rejected_rows[0]["reason"], "no_improvement")


if __name__ == "__main__":
    unittest.main()
