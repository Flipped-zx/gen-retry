from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.retry_plan_batch import RetryPlanBatchConfig, run_retry_plan_batch  # noqa: E402
from gen_retry.teachers.mock_teacher import MockTeacher  # noqa: E402


class RetryPlanBatchTest(unittest.TestCase):
    def test_batch_builds_packages_and_retry_actions_from_eval_reports(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            manifest = root / "manifest.jsonl"
            plans = root / "plans"
            eval_reports = root / "normalized_reports.jsonl"
            diagnostic_jobs = root / "diagnostic_jobs.jsonl"
            packages = root / "packages"
            outputs = root / "outputs"
            trajectories = root / "trajectories"
            plans.mkdir()

            prompt_id = "geneval2_batch_001"
            candidate_id = f"{prompt_id}_cand_00"
            manifest.write_text(
                json.dumps(
                    {
                        "candidate_id": candidate_id,
                        "candidate_index": 0,
                        "sample_id": prompt_id,
                        "prompt_index": 0,
                        "original_prompt": "two green apples on a plate",
                        "generation_prompt": "A clear image of exactly two green apples on a plate.",
                        "image_path": str(root / "not_local.png"),
                        "seed": 1000,
                        "metadata": {
                            "prompt_id": prompt_id,
                            "prompt": "two green apples on a plate",
                            "source_index": 11,
                            "skills": ["count", "attribute", "object"],
                            "vqa_list": [["How many apples are in the image?", "two"]],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (plans / f"{prompt_id}.json").write_text(
                json.dumps(
                    {
                        "initial_plan": {
                            "action_type": "initial_plan",
                            "parsed_constraints": {
                                "objects": ["apples", "plate"],
                                "counts": {"apples": 2},
                                "attributes": {"apples": "green"},
                                "relations": ["apples on plate"],
                            },
                            "selected_skills": ["quantity_counting", "attribute_binding", "object_presence"],
                            "generation_strategy": "Make the apples separated and countable.",
                            "initial_prompt": "A clear image of exactly two green apples on a plate.",
                            "generation_guards": ["No extra apples."],
                        }
                    }
                ),
                encoding="utf-8",
            )
            eval_reports.write_text(
                json.dumps(
                    {
                        "candidate_id": candidate_id,
                        "normalized_report": {
                            "score": 0.5,
                            "passed_constraints": [
                                {
                                    "type": "color_mismatch",
                                    "target": "apples",
                                    "expected": "green",
                                    "detected": "green",
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
            diagnostic_jobs.write_text(
                json.dumps({"candidate_id": candidate_id, "image_path": str(root / "not_local.png")}) + "\n",
                encoding="utf-8",
            )

            summary = run_retry_plan_batch(
                RetryPlanBatchConfig(
                    manifest_path=manifest,
                    package_dir=packages,
                    output_dir=outputs,
                    trajectory_dir=trajectories,
                    initial_plan_dir=plans,
                    eval_results_path=eval_reports,
                    diagnostic_jobs_path=diagnostic_jobs,
                    limit=1,
                ),
                teacher=MockTeacher(),
            )

            self.assertEqual(summary["status"], "ok")
            self.assertEqual(summary["retry_actions_written"], 1)
            self.assertEqual(summary["failed"], 0)
            manifest_rows = [
                json.loads(line)
                for line in (outputs / "retry_action_manifest.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(manifest_rows), 1)
            output_package = json.loads(Path(manifest_rows[0]["output_path"]).read_text(encoding="utf-8"))
            self.assertFalse(output_package["stop"]["should_stop"])
            self.assertEqual(output_package["teacher_action"]["action_type"], "retry_replan")
            self.assertEqual(output_package["teacher_request"]["candidate_id"], candidate_id)
            self.assertEqual(summary["input_preflight"]["diagnostic_job_count"], 1)
            self.assertTrue((outputs / "retry_input_preflight.json").exists())


if __name__ == "__main__":
    unittest.main()
