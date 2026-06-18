from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.data.exporters import export_sft_record


class ExportersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.row = json.loads(
            (ROOT / "data" / "processed" / "geneval_retry_sft_5_full.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()[0]
        )

    def test_qwen_export_is_assistant_only(self) -> None:
        exported = export_sft_record(self.row, "qwen")
        self.assertEqual(exported["format"], "qwen_chat")
        self.assertTrue(exported["messages"])
        self.assertTrue(all(message["role"] == "assistant" for message in exported["messages"]))

    def test_sharegpt_export_trains_only_gpt_turn(self) -> None:
        exported = export_sft_record(self.row, "sharegpt")
        self.assertEqual(exported["trainable_from"], ["gpt"])
        self.assertEqual([message["from"] for message in exported["conversations"]], ["human", "gpt"])

    def test_exports_exclude_raw_detector_metadata_from_targets(self) -> None:
        for export_format in ("qwen", "sharegpt", "trl"):
            exported = export_sft_record(self.row, export_format)
            text = json.dumps(exported, ensure_ascii=False, sort_keys=True)
            self.assertNotIn('"bbox"', text)
            self.assertNotIn('"score"', text)
            self.assertNotIn("<tool_response>", text)
            self.assertNotIn("raw_detector_outputs", text)
            self.assertIn("<repair_prompt>", text)
            self.assertIn("query_skill", text)


if __name__ == "__main__":
    unittest.main()
