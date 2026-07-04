from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NormalizeGeneval2ResultsScriptTest(unittest.TestCase):
    def test_official_scores_with_retry_benchmark_write_candidate_id(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            scores = root / "raw_score_lists.json"
            benchmark = root / "eval_benchmark.jsonl"
            output = root / "normalized_reports.jsonl"
            candidate_id = "geneval2_001_cand_00"
            scores.write_text(json.dumps([[0, 1]]), encoding="utf-8")
            benchmark.write_text(
                json.dumps(
                    {
                        "prompt": candidate_id,
                        "original_prompt": "two red apples on a table",
                        "prompt_id": "geneval2_001",
                        "candidate_id": candidate_id,
                        "candidate_index": 0,
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

            subprocess.run(
                [
                    sys.executable,
                    "scripts/normalize_geneval2_results.py",
                    "--input",
                    str(scores),
                    "--benchmark-data",
                    str(benchmark),
                    "--aggregate-by",
                    "candidate_id",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["candidate_id"], candidate_id)
            self.assertEqual(rows[0]["group_id"], candidate_id)
            self.assertEqual(rows[0]["prompt_id"], "geneval2_001")
            self.assertEqual(rows[0]["normalized_report"]["failed_constraints"][0]["type"], "count_mismatch")


if __name__ == "__main__":
    unittest.main()
