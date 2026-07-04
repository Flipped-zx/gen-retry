from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.offline_planner import (
    EvalConfig,
    StopConfig,
    process_generation_package,
    validate_raw_trajectory,
    validate_retry_action_package,
)
from gen_retry.teachers.mock_teacher import MockTeacher


class OfflinePlannerTest(unittest.TestCase):
    def test_process_generation_package_and_resume_trajectory(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            incoming = root / "incoming"
            images = root / "images"
            outgoing = root / "outgoing"
            trajectories = root / "trajectories"
            incoming.mkdir()
            images.mkdir()
            image0 = images / "attempt0.png"
            image1 = images / "attempt1.png"
            image0.write_bytes(b"fake image")
            image1.write_bytes(b"fake image")

            package0 = _package(
                image_path=image0,
                round_id=0,
                prompt_used="a visible dog",
                evaluation={
                    "score": 0.4,
                    "passed_constraints": [],
                    "failed_constraints": [
                        {
                            "type": "missing_object",
                            "target": "dog",
                            "expected": "present",
                            "detected": "missing",
                        }
                    ],
                    "uncertain_constraints": [],
                    "critical_failure_types": ["missing_object"],
                },
            )
            path0 = incoming / "round0.json"
            path0.write_text(json.dumps(package0), encoding="utf-8")

            result0 = process_generation_package(
                path0,
                output_dir=outgoing,
                trajectory_dir=trajectories,
                teacher=MockTeacher(),
                stop_config=StopConfig(max_retry=3),
                eval_config=EvalConfig(),
            )
            out0 = result0["output_package"]
            trajectory0 = result0["trajectory"]
            self.assertEqual(validate_retry_action_package(out0), [])
            self.assertFalse(out0["stop"]["should_stop"])
            self.assertEqual(out0["status"], "retry_ready")
            self.assertEqual(out0["teacher_action"]["action_type"], "retry_replan")
            self.assertEqual(out0["retry_ready_action"]["action_type"], "retry_replan")
            self.assertEqual(out0["teacher_action"]["branch_source"], "latest")
            self.assertTrue(out0["teacher_action"]["retry_prompt"])
            self.assertIsNone(out0["memory"]["score_delta_from_previous"])
            self.assertEqual(out0["memory"]["score_delta_from_best"], 0.0)
            self.assertEqual(out0["memory"]["current_round"], 0)
            self.assertEqual(out0["memory"]["previous_action"]["action_type"], "initial_plan")
            self.assertEqual(out0["memory"]["persistent_failures"][0]["target"], "dog")
            self.assertEqual(out0["memory"]["new_failures"], [])
            self.assertEqual(out0["teacher_request"]["retry_round"], 1)
            self.assertEqual(out0["teacher_request"]["previous_action"]["action_type"], "initial_plan")
            self.assertEqual(trajectory0["status"], "retry_ready")
            self.assertEqual(trajectory0["retry_ready_action"]["action_type"], "retry_replan")
            self.assertEqual(trajectory0["attempts"][0]["planner_action"]["action_type"], "initial_plan")

            package1 = _package(
                image_path=image1,
                round_id=1,
                prompt_used=out0["teacher_action"]["retry_prompt"],
                previous_action=out0["teacher_action"],
                evaluation={
                    "score": 1.0,
                    "passed_constraints": [
                        {
                            "type": "missing_object",
                            "target": "dog",
                            "expected": "present",
                            "detected": "visible",
                        }
                    ],
                    "failed_constraints": [],
                    "uncertain_constraints": [],
                    "critical_failure_types": [],
                },
            )
            path1 = incoming / "round1.json"
            path1.write_text(json.dumps(package1), encoding="utf-8")
            result1 = process_generation_package(
                path1,
                output_dir=outgoing,
                trajectory_dir=trajectories,
                teacher=MockTeacher(),
                stop_config=StopConfig(max_retry=3),
                eval_config=EvalConfig(),
            )
            out1 = result1["output_package"]
            trajectory = result1["trajectory"]
            self.assertTrue(out1["stop"]["should_stop"])
            self.assertEqual(out1["stop"]["reason"], "passed")
            self.assertIsNone(out1["teacher_action"])
            self.assertEqual(out1["memory"]["best_so_far_round"], 1)
            self.assertEqual(out1["memory"]["fixed_constraints"][0]["target"], "dog")
            self.assertEqual(trajectory["attempts"][1]["planner_action"]["action_type"], "retry_replan")
            self.assertEqual(trajectory["attempts"][1]["transition"]["transition_type"], "passed_after_retry")
            self.assertEqual(validate_raw_trajectory(trajectory, base_dir=root), [])


def _package(
    *,
    image_path: Path,
    round_id: int,
    prompt_used: str,
    evaluation: dict,
    previous_action: dict | None = None,
) -> dict:
    return {
        "schema_version": "v1",
        "trajectory_id": "traj_001",
        "prompt_id": "prompt_001",
        "candidate_id": "candidate_a",
        "round": round_id,
        "source": {
            "dataset": "geneval2",
            "source_index": 0,
            "original_prompt": "a visible dog",
            "skills": ["object"],
            "atom_count": 1,
            "vqa_list": [["Is there a dog?", "yes"]],
        },
        "generation": {
            "generator_name": "qwen-image-2512",
            "prompt_used": prompt_used,
            "seed": 123,
            "image_path": str(image_path),
            "image_id": f"img_{round_id}",
            "generation_metadata": {},
        },
        "evaluation": evaluation,
        "previous_action": previous_action,
        "retry_history": [],
    }


if __name__ == "__main__":
    unittest.main()
