from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.collectors.qwen_geneval_batch import QwenGenevalBatchCollector, format_command


class QwenGenevalBatchTest(unittest.TestCase):
    def test_plans_four_candidates_per_prompt_across_gpus(self) -> None:
        with TemporaryDirectory() as tmp:
            prompts = Path(tmp) / "prompts.jsonl"
            prompts.write_text(
                json.dumps(
                    {
                        "id": "sample_a",
                        "prompt": "three red apples",
                        "category": "counting",
                        "expected": {"count": {"apple": 3}},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            collector = QwenGenevalBatchCollector(
                prompts_path=prompts,
                output_dir=Path(tmp) / "run",
                images_per_prompt=4,
                gpus=["0", "1", "2", "3"],
                run_id="run_test",
            )
            jobs = collector.plan_jobs()
            self.assertEqual(len(jobs), 4)
            self.assertEqual([job.gpu for job in jobs], ["0", "1", "2", "3"])
            self.assertEqual(
                jobs[0].qwen_model_path,
                "/home/develop/biocloudplantform/xxr/models/Qwen-Image-2512",
            )
            manifest = collector.write_manifest(jobs)
            self.assertEqual(len(manifest.read_text(encoding="utf-8").splitlines()), 4)

    def test_command_template_shell_quotes_prompt_and_model_path(self) -> None:
        with TemporaryDirectory() as tmp:
            prompts = Path(tmp) / "prompts.jsonl"
            prompts.write_text(
                json.dumps({"id": "sample_a", "prompt": "a red apple"})
                + "\n",
                encoding="utf-8",
            )
            collector = QwenGenevalBatchCollector(
                prompts_path=prompts,
                output_dir=Path(tmp) / "run",
                run_id="run_test",
            )
            job = collector.plan_jobs()[0]
            command = format_command("echo {prompt} {seed} {image_path} {qwen_model_path}", job)
            self.assertIn("'a red apple'", command)
            self.assertIn(str(job.seed), command)
            self.assertIn("/home/develop/biocloudplantform/xxr/models/Qwen-Image-2512", command)


if __name__ == "__main__":
    unittest.main()
