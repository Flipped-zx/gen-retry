from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.collectors.collect_episodes import EpisodeCollector, is_passed, should_continue
from gen_retry.evaluators.mock_geneval import MockGenevalEvaluator
from gen_retry.filters.validate_episode import validate_episode
from gen_retry.generators.mock_generator import MockGenerator
from gen_retry.schemas.reports import NormalizedConstraint, NormalizedEvalReport
from gen_retry.teachers.mock_teacher import MockTeacher


class MockLoopTest(unittest.TestCase):
    def test_stop_rules(self) -> None:
        passed = NormalizedEvalReport(score=1.0)
        self.assertTrue(is_passed(passed))
        failed = NormalizedEvalReport(
            score=0.96,
            failed_constraints=[NormalizedConstraint(type="missing_object", target="dog")],
            critical_failure_types=["missing_object"],
        )
        self.assertFalse(is_passed(failed))
        self.assertFalse(should_continue(failed, 0, 2).should_stop)
        self.assertTrue(should_continue(failed, 2, 2).should_stop)

    def test_mock_collector_saves_valid_episode_without_image_edit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = [
                {
                    "prompt": "a red apple",
                    "mock_reports": [
                        {
                            "score": 0.5,
                            "failed_constraints": [
                                {"type": "missing_object", "target": "apple", "expected": "present", "detected": "missing"}
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
            episode = collector.run_episode("a red apple", episode_id="episode_test")
            self.assertEqual(episode.final_outcome, "passed_after_retry")
            self.assertEqual(validate_episode(episode), [])
            payload = (root / "episodes" / "episode_test.json").read_text(encoding="utf-8")
            self.assertNotIn("image_edit", payload)
            self.assertIn('"retry_prompt"', payload)


if __name__ == "__main__":
    unittest.main()
