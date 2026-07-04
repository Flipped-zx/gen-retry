from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.quality.geneval2_retry_inputs import check_geneval2_retry_inputs  # noqa: E402
from gen_retry.utils.io import write_json, write_jsonl  # noqa: E402


class Geneval2RetryInputsTest(unittest.TestCase):
    def test_complete_inputs_pass(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            package, package_manifest, jobs, reports = _write_inputs(root, include_report=True)
            report = check_geneval2_retry_inputs(
                package_manifest_path=package_manifest,
                diagnostic_jobs_path=jobs,
                eval_results_path=reports,
                expected_count=1,
            )
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["package_count"], 1)
            self.assertEqual(report["eval_report_count"], 1)
            self.assertEqual(report["retry_candidate_count"], 1)
            self.assertEqual(report["failure_type_counts"], {"count_mismatch": 1})
            self.assertTrue(package.exists())

    def test_missing_eval_report_fails(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            _, package_manifest, jobs, reports = _write_inputs(root, include_report=False)
            report = check_geneval2_retry_inputs(
                package_manifest_path=package_manifest,
                diagnostic_jobs_path=jobs,
                eval_results_path=reports,
                expected_count=1,
            )
            self.assertEqual(report["status"], "fail")
            self.assertTrue(any(issue["code"] == "eval_report_missing_for_package" for issue in report["issues"]))


def _write_inputs(root: Path, *, include_report: bool) -> tuple[Path, Path, Path, Path]:
    candidate_id = "cand_00"
    package = root / "package.json"
    package_manifest = root / "package_manifest.jsonl"
    jobs = root / "diagnostic_jobs.jsonl"
    reports = root / "normalized_reports.jsonl"
    write_json(
        package,
        {
            "metadata": {"teacher_uses_image_bytes": False},
            "previous_initial_plan": {
                "action_type": "initial_plan",
                "parsed_constraints": {"objects": ["apples"], "counts": {}, "attributes": {}, "relations": []},
                "selected_skills": ["quantity_counting"],
                "generation_strategy": "Make the objects countable.",
                "initial_prompt": "Two apples.",
                "generation_guards": [],
            },
        },
    )
    write_jsonl(
        package_manifest,
        [
            {
                "candidate_id": candidate_id,
                "package_path": str(package),
            }
        ],
    )
    write_jsonl(jobs, [{"candidate_id": candidate_id, "image_path": "image.png"}])
    rows = []
    if include_report:
        rows.append(
            {
                "candidate_id": candidate_id,
                "normalized_report": {
                    "score": 0.5,
                    "passed_constraints": [],
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
    write_jsonl(reports, rows)
    return package, package_manifest, jobs, reports


if __name__ == "__main__":
    unittest.main()
