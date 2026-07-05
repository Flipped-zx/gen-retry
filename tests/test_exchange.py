from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.exchange import (  # noqa: E402
    build_retry_continuation_packages,
    package_gpu_to_api_handoff,
)


class ExchangeTest(unittest.TestCase):
    def test_package_gpu_to_api_handoff_validates_candidate_coverage(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            generation_manifest = root / "generation_manifest.jsonl"
            geneval2_dir = root / "geneval2"
            output_dir = root / "exchange" / "gpu_to_api" / "run"
            geneval2_dir.mkdir()
            _write_jsonl(
                generation_manifest,
                [
                    _generation_row(
                        candidate_id="prompt001_cand_00_retry01_cand_00",
                        source_trajectory_path=str(root / "trajectory.json"),
                    )
                ],
            )
            _write_jsonl(
                geneval2_dir / "normalized_reports.jsonl",
                [_report_row(candidate_id="prompt001_cand_00_retry01_cand_00", score=0.8)],
            )
            _write_jsonl(
                geneval2_dir / "diagnostic_jobs.jsonl",
                [{"candidate_id": "prompt001_cand_00_retry01_cand_00"}],
            )

            summary = package_gpu_to_api_handoff(
                generation_manifest_path=generation_manifest,
                geneval2_dir=geneval2_dir,
                output_dir=output_dir,
                expected_count=1,
            )

            self.assertEqual(summary["status"], "ok")
            self.assertEqual(summary["counts"]["generation_manifest"], 1)
            self.assertTrue((output_dir / "generation_manifest.jsonl").exists())
            self.assertTrue((output_dir / "normalized_reports.jsonl").exists())
            self.assertTrue((output_dir / "handoff_manifest.json").exists())

    def test_build_retry_continuation_packages_preserves_source_trajectory_identity(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            trajectory_path = root / "raw_trajectories" / "prompt001__prompt001_cand_00.json"
            handoff_dir = root / "exchange" / "gpu_to_api" / "run"
            package_dir = root / "packages"
            trajectory_path.parent.mkdir()
            handoff_dir.mkdir(parents=True)
            retry_action = _retry_action()
            _write_json(trajectory_path, _trajectory(trajectory_path, retry_action))
            _write_jsonl(
                handoff_dir / "generation_manifest.jsonl",
                [
                    _generation_row(
                        candidate_id="prompt001_cand_00_retry01_cand_00",
                        source_trajectory_path=str(trajectory_path),
                        previous_action=retry_action,
                    )
                ],
            )
            _write_jsonl(
                handoff_dir / "normalized_reports.jsonl",
                [_report_row(candidate_id="prompt001_cand_00_retry01_cand_00", score=1.0)],
            )

            summary = build_retry_continuation_packages(
                gpu_handoff_dir=handoff_dir,
                output_dir=package_dir,
                round_id=1,
            )

            self.assertEqual(summary["status"], "ok")
            manifest = _read_jsonl(package_dir / "package_manifest.jsonl")
            self.assertEqual(len(manifest), 1)
            package = json.loads(Path(manifest[0]["package_path"]).read_text(encoding="utf-8"))
            self.assertEqual(package["trajectory_id"], "prompt001")
            self.assertEqual(package["prompt_id"], "prompt001")
            self.assertEqual(package["candidate_id"], "prompt001_cand_00")
            self.assertEqual(package["round"], 1)
            self.assertEqual(package["generation"]["image_id"], "prompt001_cand_00_retry01_cand_00")
            self.assertEqual(package["previous_action"], retry_action)
            self.assertEqual(package["evaluation"]["score"], 1.0)
            self.assertTrue(package["metadata"]["image_path_is_artifact_reference"])


def _generation_row(
    *,
    candidate_id: str,
    source_trajectory_path: str,
    previous_action: dict | None = None,
) -> dict:
    metadata = {
        "prompt_id": "prompt001_cand_00_retry01",
        "source": "geneval2",
        "dataset": "geneval2",
        "source_index": 1,
        "prompt": "a visible dog",
        "skills": ["object"],
        "vqa_list": [["Is there a dog?", "yes"]],
        "generation_prompt": "a crisp image with one visible dog",
        "generation_prompt_source": "teacher_retry_replan",
        "retry_round": 1,
        "original_prompt_id": "prompt001",
        "original_candidate_id": "prompt001_cand_00",
        "source_trajectory_path": source_trajectory_path,
    }
    if previous_action is not None:
        metadata["previous_action"] = previous_action
    return {
        "sample_id": "prompt001_cand_00_retry01",
        "candidate_id": candidate_id,
        "prompt_index": 0,
        "candidate_index": 0,
        "seed": 123,
        "prompt": "a crisp image with one visible dog",
        "original_prompt": "a visible dog",
        "generation_prompt": "a crisp image with one visible dog",
        "generation_prompt_source": "teacher_retry_replan",
        "image_path": f"data/qwen_retry/00000/samples/{candidate_id}.png",
        "metadata": metadata,
    }


def _report_row(*, candidate_id: str, score: float) -> dict:
    return {
        "candidate_id": candidate_id,
        "score": score,
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
    }


def _trajectory(path: Path, retry_action: dict) -> dict:
    initial_plan = {
        "action_type": "initial_plan",
        "parsed_constraints": {"objects": ["dog"], "counts": {}, "attributes": {}, "relations": []},
        "selected_skills": ["object_presence"],
        "generation_strategy": "Make the dog large and unobstructed.",
        "initial_prompt": "a visible dog",
        "generation_guards": ["Do not hide the dog."],
    }
    return {
        "schema_version": "v1",
        "trajectory_id": "prompt001",
        "prompt_id": "prompt001",
        "candidate_id": "prompt001_cand_00",
        "source": {
            "dataset": "geneval2",
            "source": "geneval2",
            "source_index": 1,
            "original_prompt": "a visible dog",
            "prompt": "a visible dog",
            "prompt_id": "prompt001",
            "skills": ["object"],
            "vqa_list": [["Is there a dog?", "yes"]],
        },
        "generator_name": "qwen-image-2512",
        "initial_plan": initial_plan,
        "attempts": [
            {
                "round": 0,
                "attempt_type": "initial_generation",
                "generation": {
                    "generator_name": "qwen-image-2512",
                    "prompt_used": "a visible dog",
                    "seed": 123,
                    "image_id": "prompt001_cand_00",
                    "image_path": "data/qwen_initial/00000/samples/00000.png",
                    "generation_metadata": {},
                },
                "previous_action": initial_plan,
                "evaluation": {
                    "score": 0.0,
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
                "planner_action": initial_plan,
                "transition": {"transition_type": "initial"},
            }
        ],
        "memory": {},
        "latest_round": 0,
        "status": "retry_ready",
        "latest_teacher_action": retry_action,
        "retry_ready_action": retry_action,
        "metadata": {"last_input_package_path": str(path)},
    }


def _retry_action() -> dict:
    return {
        "action_type": "retry_replan",
        "decision": "regenerate",
        "failure_types": ["missing_object"],
        "diagnosis": "The dog was missing.",
        "previous_plan_error": {"error_source": "prompt_underemphasis", "details": "Dog not explicit enough."},
        "skill_revision": {
            "previous_skills": ["object_presence"],
            "new_skills": ["object_presence", "clarity_visibility"],
            "reason": "Emphasize visibility.",
        },
        "preserve_constraints": [],
        "repair_constraints": ["dog must be visible"],
        "regeneration_strategy": "Make the dog the main subject.",
        "retry_prompt": "a crisp image with one visible dog",
        "expected_improvement": ["dog visible"],
        "regression_risks": ["avoid cropping"],
        "branch_source_round": 0,
        "branch_source": "latest",
    }


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


if __name__ == "__main__":
    unittest.main()
