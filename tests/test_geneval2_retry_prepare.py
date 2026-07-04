from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.geneval2_retry_prepare import (  # noqa: E402
    Geneval2RetryPrepareConfig,
    prepare_geneval2_retry_inputs,
)


class Geneval2RetryPrepareTest(unittest.TestCase):
    def test_prepare_from_raw_score_lists_is_ready_for_teacher(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            fixture = _write_fixture(root)
            summary = prepare_geneval2_retry_inputs(
                Geneval2RetryPrepareConfig(
                    manifest_path=fixture["manifest"],
                    package_dir=fixture["packages"],
                    initial_plan_dir=fixture["plans"],
                    diagnostic_jobs_path=fixture["diagnostic_jobs"],
                    raw_score_lists_path=fixture["raw_scores"],
                    benchmark_data_path=fixture["benchmark"],
                    limit=1,
                )
            )

            self.assertEqual(summary["status"], "ready_for_teacher")
            self.assertEqual(summary["normalized_summary"]["report_count"], 1)
            self.assertEqual(summary["package_build"]["package_count"], 1)
            self.assertEqual(summary["preflight"]["status"], "pass")
            package_manifest = Path(summary["package_manifest_path"])
            row = json.loads(package_manifest.read_text(encoding="utf-8").splitlines()[0])
            package = json.loads(Path(row["package_path"]).read_text(encoding="utf-8"))
            self.assertEqual(package["candidate_id"], fixture["candidate_id"])
            self.assertEqual(package["evaluation"]["failed_constraints"][0]["type"], "count_mismatch")
            self.assertFalse(package["metadata"]["teacher_uses_image_bytes"])

    def test_cli_prepare_from_raw_score_lists(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            fixture = _write_fixture(root)
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/prepare_geneval2_retry_inputs.py",
                    "--manifest",
                    str(fixture["manifest"]),
                    "--package-dir",
                    str(fixture["packages"]),
                    "--initial-plan-dir",
                    str(fixture["plans"]),
                    "--diagnostic-jobs",
                    str(fixture["diagnostic_jobs"]),
                    "--raw-score-lists",
                    str(fixture["raw_scores"]),
                    "--benchmark-data",
                    str(fixture["benchmark"]),
                    "--limit",
                    "1",
                ],
                cwd=ROOT,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            summary = json.loads(result.stdout)
            self.assertEqual(summary["status"], "ready_for_teacher")
            self.assertTrue(Path(summary["normalized_reports_path"]).exists())
            self.assertTrue(Path(summary["preflight_report_path"]).exists())


def _write_fixture(root: Path) -> dict[str, Path | str]:
    candidate_id = "geneval2_001_cand_00"
    prompt_id = "geneval2_001"
    manifest = root / "generation_manifest.jsonl"
    plans = root / "plans"
    packages = root / "packages"
    diagnostic_jobs = root / "diagnostic_jobs.jsonl"
    raw_scores = root / "raw_score_lists.json"
    benchmark = root / "eval_benchmark.jsonl"
    plans.mkdir()
    manifest.write_text(
        json.dumps(
            {
                "candidate_id": candidate_id,
                "candidate_index": 0,
                "sample_id": prompt_id,
                "prompt_index": 0,
                "original_prompt": "two red apples on a table",
                "generation_prompt": "A clear image of exactly two red apples on a table.",
                "image_path": str(root / "not_local.png"),
                "metadata": {
                    "prompt_id": prompt_id,
                    "prompt": "two red apples on a table",
                    "source_index": 17,
                    "skills": ["count", "object"],
                    "vqa_list": [
                        ["How many apples are in the image?", "two"],
                        ["Are there apples in the image?", "Yes"],
                    ],
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
                        "objects": ["apples", "table"],
                        "counts": {"apples": 2},
                        "attributes": {"apples": "red"},
                        "relations": ["apples on table"],
                    },
                    "selected_skills": ["quantity_counting", "object_presence", "attribute_binding"],
                    "generation_strategy": "Make the apples separate and easy to count.",
                    "initial_prompt": "A clear image of exactly two red apples on a table.",
                    "generation_guards": ["No extra apples."],
                }
            }
        ),
        encoding="utf-8",
    )
    diagnostic_jobs.write_text(
        json.dumps({"candidate_id": candidate_id, "image_path": str(root / "not_local.png")}) + "\n",
        encoding="utf-8",
    )
    raw_scores.write_text(json.dumps([[0, 1]]), encoding="utf-8")
    benchmark.write_text(
        json.dumps(
            {
                "prompt": candidate_id,
                "original_prompt": "two red apples on a table",
                "prompt_id": prompt_id,
                "candidate_id": candidate_id,
                "candidate_index": 0,
                "source_index": 17,
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
    return {
        "candidate_id": candidate_id,
        "manifest": manifest,
        "plans": plans,
        "packages": packages,
        "diagnostic_jobs": diagnostic_jobs,
        "raw_scores": raw_scores,
        "benchmark": benchmark,
    }


if __name__ == "__main__":
    unittest.main()
