from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.schemas.episode_schema import (
    Attempt,
    Constraint,
    Episode,
    NormalizedGenevalReport,
    TeacherAction,
)


class RetryEpisodeSchemaTest(unittest.TestCase):
    def test_episode_round_trip(self) -> None:
        episode = Episode(
            id="episode_test",
            original_prompt="three red apples",
            attempts=[
                Attempt(
                    round=0,
                    attempt_type="initial_generation",
                    prompt="three red apples",
                    image_path="data/images/mock.png",
                    geneval_report=NormalizedGenevalReport(
                        score=0.5,
                        failed_constraints=[
                            Constraint(
                                type="count_mismatch",
                                target="apple",
                                expected=3,
                                detected=2,
                                status="failed",
                            )
                        ],
                    ),
                    teacher_action=TeacherAction(
                        decision="retry",
                        failure_types=["count_mismatch"],
                        diagnosis="count mismatch",
                        action_type="image_edit",
                        skill="quantity_counting",
                        edit_instruction="add one apple",
                    ),
                )
            ],
            final_outcome="failed_after_budget",
        )
        restored = Episode.from_dict(episode.to_dict())
        self.assertEqual(restored.id, "episode_test")
        self.assertEqual(restored.attempts[0].teacher_action.decision, "retry")
        self.assertEqual(restored.attempts[0].geneval_report.failed_constraints[0].type, "count_mismatch")


if __name__ == "__main__":
    unittest.main()
