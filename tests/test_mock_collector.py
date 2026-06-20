from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.collectors.retry_episode_collector import RetryEpisodeCollector
from gen_retry.evaluators.mock_geneval_evaluator import MockGenevalEvaluator
from gen_retry.filters.validate_episode import validate_episode
from gen_retry.generators.mock_initial_generator import MockInitialGenerator, MockRetryExecutor
from gen_retry.teachers.mock_teacher import MockTeacher


class MockCollectorTest(unittest.TestCase):
    def test_mock_collector_creates_valid_episode(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = [
                {
                    "prompt": "three red apples",
                    "mock_reports": [
                        {
                            "score": 0.5,
                            "passed_constraints": [],
                            "failed_constraints": [
                                {
                                    "type": "count_mismatch",
                                    "target": "apple",
                                    "expected": 3,
                                    "detected": 2,
                                }
                            ],
                            "uncertain_constraints": [],
                        },
                        {
                            "score": 1.0,
                            "passed_constraints": [
                                {
                                    "type": "count_mismatch",
                                    "target": "apple",
                                    "expected": 3,
                                    "detected": 3,
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
            episode = collector.run_episode("three red apples", episode_id="episode_test")
            self.assertEqual(episode.final_outcome, "passed_after_retry")
            self.assertEqual(validate_episode(episode, mock_mode=True), [])
            self.assertTrue((root / "episodes" / "episode_test.json").exists())


if __name__ == "__main__":
    unittest.main()
