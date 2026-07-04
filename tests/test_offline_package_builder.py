from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.offline_package_builder import build_generation_packages_from_manifest
from gen_retry.offline_planner import (
    EvalConfig,
    StopConfig,
    process_generation_package,
    validate_offline_object,
)
from gen_retry.teachers.mock_teacher import MockTeacher


class OfflinePackageBuilderTest(unittest.TestCase):
    def test_builds_round0_package_and_plans_without_local_image(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            manifest = root / "manifest.jsonl"
            plan_dir = root / "plans"
            package_dir = root / "packages"
            outgoing = root / "outgoing"
            trajectories = root / "trajectories"
            plan_dir.mkdir()

            prompt_id = "geneval2_test_001"
            candidate_id = f"{prompt_id}_cand_00"
            missing_image = root / "missing.png"
            manifest.write_text(
                json.dumps(
                    {
                        "candidate_id": candidate_id,
                        "candidate_index": 0,
                        "sample_id": prompt_id,
                        "prompt_index": 0,
                        "original_prompt": "one red cube on top of two blue spheres",
                        "generation_prompt": "A clear scene with one red cube on top of two blue spheres.",
                        "generation_prompt_source": "initial_plan",
                        "image_path": str(missing_image),
                        "seed": 1000,
                        "metadata": {
                            "prompt_id": prompt_id,
                            "prompt": "one red cube on top of two blue spheres",
                            "source": "geneval2",
                            "source_index": 7,
                            "skills": ["count", "attribute", "position", "object"],
                            "atom_count": 4,
                            "vqa_list": [["How many cubes are in the image?", "one"]],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (plan_dir / f"{prompt_id}.json").write_text(
                json.dumps(
                    {
                        "initial_plan": {
                            "action_type": "initial_plan",
                            "parsed_constraints": {
                                "objects": ["cube", "spheres"],
                                "counts": {"cube": 1, "spheres": 2},
                                "attributes": {"cube": "red", "spheres": "blue"},
                                "relations": ["cube on top of spheres"],
                            },
                            "selected_skills": [
                                "quantity_counting",
                                "attribute_binding",
                                "spatial_layout",
                                "object_presence",
                            ],
                            "generation_strategy": "Keep objects distinct and countable.",
                            "initial_prompt": "A clear scene with one red cube on top of two blue spheres.",
                            "generation_guards": ["No extra cubes.", "No extra spheres."],
                        }
                    }
                ),
                encoding="utf-8",
            )
            eval_results = root / "eval.jsonl"
            eval_results.write_text(
                json.dumps(
                    {
                        "candidate_id": candidate_id,
                        "normalized_report": {
                            "score": 0.5,
                            "passed_constraints": [
                                {
                                    "type": "color_mismatch",
                                    "target": "cube",
                                    "expected": "red",
                                    "detected": "red",
                                    "status": "passed",
                                }
                            ],
                            "failed_constraints": [
                                {
                                    "type": "count_mismatch",
                                    "target": "spheres",
                                    "expected": 2,
                                    "detected": 1,
                                    "status": "failed",
                                }
                            ],
                            "uncertain_constraints": [],
                            "critical_failure_types": ["count_mismatch"],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            summary = build_generation_packages_from_manifest(
                manifest_path=manifest,
                output_dir=package_dir,
                initial_plan_dir=plan_dir,
                eval_results_path=eval_results,
                require_initial_plan=True,
            )
            self.assertEqual(summary.package_count, 1)
            self.assertEqual(summary.missing_eval_report_count, 0)
            self.assertEqual(summary.missing_image_count, 1)

            package_manifest = (package_dir / "package_manifest.jsonl").read_text(encoding="utf-8")
            package_path = Path(json.loads(package_manifest)["package_path"])
            package = json.loads(package_path.read_text(encoding="utf-8"))
            self.assertEqual(validate_offline_object(package, base_dir=root, require_image_path_exists=False), [])
            self.assertEqual(package["previous_initial_plan"]["selected_skills"][0], "quantity_counting")
            self.assertFalse(package["metadata"]["teacher_uses_image_bytes"])

            result = process_generation_package(
                package_path,
                output_dir=outgoing,
                trajectory_dir=trajectories,
                teacher=MockTeacher(),
                stop_config=StopConfig(max_retry=3),
                eval_config=EvalConfig(),
            )
            output = result["output_package"]
            self.assertFalse(output["stop"]["should_stop"])
            self.assertEqual(output["teacher_action"]["action_type"], "retry_replan")
            self.assertIn("teacher_request", output)
            self.assertEqual(
                output["teacher_request"]["previous_selected_skills"],
                [
                    "quantity_counting",
                    "attribute_binding",
                    "spatial_layout",
                    "object_presence",
                ],
            )


if __name__ == "__main__":
    unittest.main()
