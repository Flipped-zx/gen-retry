from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.quality.retry_plan_quality import FORBIDDEN_IMAGE_INPUT_KEYS  # noqa: E402
from gen_retry.teacher_request_preview import (  # noqa: E402
    TeacherRequestPreviewConfig,
    preview_teacher_requests,
)
from gen_retry.utils.io import write_json, write_jsonl  # noqa: E402


class TeacherRequestPreviewTest(unittest.TestCase):
    def test_preview_builds_request_without_local_image_bytes(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            package, manifest = _write_package(root)
            output = root / "teacher_requests_preview.jsonl"

            summary = preview_teacher_requests(
                TeacherRequestPreviewConfig(
                    package_manifest_path=manifest,
                    output_path=output,
                )
            )

            self.assertEqual(summary["status"], "pass")
            self.assertEqual(summary["teacher_requests_written"], 1)
            row = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
            request = row["teacher_request"]
            self.assertEqual(row["package_path"], str(package))
            self.assertEqual(request["candidate_id"], "cand_00")
            self.assertEqual(request["previous_initial_plan"]["action_type"], "initial_plan")
            self.assertEqual(request["current_eval_report"]["failed_constraints"][0]["type"], "count_mismatch")
            self.assertEqual(FORBIDDEN_IMAGE_INPUT_KEYS & _deep_keys(request), set())

    def test_cli_preview(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            _, manifest = _write_package(root)
            output = root / "teacher_requests_preview.jsonl"

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/preview_geneval2_teacher_requests.py",
                    "--package-manifest",
                    str(manifest),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            summary = json.loads(result.stdout)
            self.assertEqual(summary["status"], "pass")
            self.assertTrue(output.exists())
            self.assertEqual(summary["teacher_uses_image_bytes"], False)


def _write_package(root: Path) -> tuple[Path, Path]:
    package = root / "package.json"
    manifest = root / "package_manifest.jsonl"
    payload = {
        "schema_version": "v1",
        "trajectory_id": "traj_001",
        "prompt_id": "prompt_001",
        "candidate_id": "cand_00",
        "round": 0,
        "source": {
            "dataset": "geneval2",
            "source_index": 0,
            "original_prompt": "two red apples",
            "skills": ["count", "attribute"],
            "atom_count": 2,
            "vqa_list": [["How many apples are in the image?", "two"]],
        },
        "generation": {
            "generator_name": "qwen-image-2512",
            "prompt_used": "A clear image of exactly two red apples.",
            "seed": 11,
            "image_path": str(root / "missing.png"),
            "image_id": "cand_00",
            "generation_metadata": {},
        },
        "previous_initial_plan": {
            "action_type": "initial_plan",
            "parsed_constraints": {
                "objects": ["apples"],
                "counts": {"apples": 2},
                "attributes": {"apples": "red"},
                "relations": [],
            },
            "selected_skills": ["quantity_counting", "attribute_binding"],
            "generation_strategy": "Make the apple count and color explicit.",
            "initial_prompt": "A clear image of exactly two red apples.",
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
        },
        "metadata": {"teacher_uses_image_bytes": False},
    }
    write_json(package, payload)
    write_jsonl(manifest, [{"candidate_id": "cand_00", "package_path": str(package)}])
    return package, manifest


def _deep_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key))
            keys.update(_deep_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_deep_keys(item))
    return keys


if __name__ == "__main__":
    unittest.main()
