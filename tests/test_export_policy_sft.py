from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.collectors.retry_episode_collector import RetryEpisodeCollector
from gen_retry.evaluators.mock_geneval_evaluator import MockGenevalEvaluator
from gen_retry.export.export_policy_sft import export_policy_sft
from gen_retry.generators.mock_initial_generator import MockInitialGenerator, MockRetryExecutor
from gen_retry.teachers.mock_teacher import MockTeacher


class ExportPolicySftTest(unittest.TestCase):
    def test_exporter_creates_sharegpt_jsonl(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = "two blue birds"
            records = [
                {
                    "prompt": prompt,
                    "mock_reports": [
                        {
                            "score": 0.4,
                            "passed_constraints": [],
                            "failed_constraints": [
                                {
                                    "type": "color_mismatch",
                                    "target": "bird",
                                    "expected": "blue",
                                    "detected": "green",
                                }
                            ],
                            "uncertain_constraints": [],
                        },
                        {
                            "score": 1.0,
                            "passed_constraints": [
                                {
                                    "type": "color_mismatch",
                                    "target": "bird",
                                    "expected": "blue",
                                    "detected": "blue",
                                }
                            ],
                            "failed_constraints": [],
                            "uncertain_constraints": [],
                        },
                    ],
                }
            ]
            collector = RetryEpisodeCollector(
                initial_generator=MockInitialGenerator(root / "images"),
                retry_executor=MockRetryExecutor(root / "images"),
                evaluator=MockGenevalEvaluator(records),
                teacher=MockTeacher(),
                output_dir=root / "episodes",
            )
            collector.run_episode(prompt, episode_id="episode_export")
            output = root / "sft.jsonl"
            count = export_policy_sft(root / "episodes", output)
            self.assertEqual(count, 1)
            row = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual([message["role"] for message in row["messages"]], ["system", "user", "assistant"])
            action = json.loads(row["messages"][2]["content"])
            self.assertEqual(action["decision"], "retry")
            self.assertEqual(action["skill"], "attribute_binding")


if __name__ == "__main__":
    unittest.main()
