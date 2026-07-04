from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.export.export_offline_sft import export_offline_retry_sft  # noqa: E402
from gen_retry.offline_planner import EvalConfig, StopConfig, process_generation_package  # noqa: E402
from gen_retry.teachers.mock_teacher import MockTeacher  # noqa: E402


class ExportOfflineSftTest(unittest.TestCase):
    def test_export_retry_ready_trajectory_as_step_level_sft(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            incoming = root / "incoming"
            outgoing = root / "outgoing"
            trajectories = root / "trajectories"
            images = root / "images"
            incoming.mkdir()
            images.mkdir()
            image_path = images / "initial.png"
            image_path.write_bytes(b"fake image")
            package_path = incoming / "package.json"
            package_path.write_text(json.dumps(_package(image_path)), encoding="utf-8")

            process_generation_package(
                package_path,
                output_dir=outgoing,
                trajectory_dir=trajectories,
                teacher=MockTeacher(),
                stop_config=StopConfig(max_retry=3),
                eval_config=EvalConfig(),
            )

            output = root / "offline_sft.jsonl"
            rejected = root / "offline_rejected.jsonl"
            count = export_offline_retry_sft(trajectories, output, rejected_output=rejected)

            self.assertEqual(count, 1)
            self.assertEqual(rejected.read_text(encoding="utf-8"), "")
            row = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual([message["role"] for message in row["messages"]], ["system", "user", "assistant"])
            state = json.loads(row["messages"][1]["content"])
            target = json.loads(row["messages"][2]["content"])
            self.assertEqual(state["retry_round"], 1)
            self.assertEqual(state["previous_action"]["action_type"], "initial_plan")
            self.assertEqual(state["current_eval_report"]["failed_constraints"][0]["type"], "count_mismatch")
            self.assertEqual(state["memory"]["persistent_failures"][0]["target"], "apples")
            self.assertEqual(target["action_type"], "retry_replan")
            self.assertNotIn("image_path", row["messages"][1]["content"])
            self.assertNotIn("image_id", row["messages"][1]["content"])
            self.assertNotIn("raw_report", row["messages"][1]["content"])


def _package(image_path: Path) -> dict:
    return {
        "schema_version": "v1",
        "trajectory_id": "traj_001",
        "prompt_id": "prompt_001",
        "candidate_id": "cand_00",
        "round": 0,
        "source": {
            "dataset": "geneval2",
            "source_index": 0,
            "original_prompt": "two red apples on a plate",
            "skills": ["count", "attribute"],
            "atom_count": 2,
            "vqa_list": [["How many apples are in the image?", "two"]],
        },
        "generation": {
            "generator_name": "qwen-image-2512",
            "prompt_used": "A clear image of exactly two red apples on a plate.",
            "seed": 1000,
            "image_path": str(image_path),
            "image_id": "cand_00",
            "generation_metadata": {},
        },
        "previous_initial_plan": {
            "action_type": "initial_plan",
            "parsed_constraints": {
                "objects": ["apples", "plate"],
                "counts": {"apples": 2},
                "attributes": {"apples": "red"},
                "relations": ["apples on plate"],
            },
            "selected_skills": ["quantity_counting", "attribute_binding", "object_presence"],
            "generation_strategy": "Make the apple count and color explicit.",
            "initial_prompt": "A clear image of exactly two red apples on a plate.",
            "generation_guards": ["No extra apples."],
        },
        "previous_action": None,
        "retry_history": [],
        "evaluation": {
            "score": 0.5,
            "passed_constraints": [
                {
                    "type": "color_mismatch",
                    "target": "apples",
                    "expected": "red",
                    "detected": "red",
                    "status": "passed",
                }
            ],
            "failed_constraints": [
                {
                    "type": "count_mismatch",
                    "target": "apples",
                    "expected": 2,
                    "detected": 1,
                    "status": "failed",
                    "details": {"raw": {"image_bytes": "must not leak"}},
                }
            ],
            "uncertain_constraints": [],
            "critical_failure_types": ["count_mismatch"],
            "raw_report": {"rows": [{"image_id": "cand_00"}]},
        },
    }


if __name__ == "__main__":
    unittest.main()
