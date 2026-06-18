#!/usr/bin/env python3
"""Stdlib-only quality checks for exported Gen-Retry SFT files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(r"(?i)\bapi[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9._-]{16,}"),
)

RAW_METADATA_TOKENS = (
    '"bbox"',
    '"score"',
    "raw_detector_outputs",
    "tool_observations",
    "mock_retry_diagnostic",
    "generated_image_metadata",
    "<tool_response>",
)

REQUIRED_TARGET_MARKERS = (
    "<tool_call>",
    "query_skill",
    "<repair_prompt>",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check exported SFT JSONL files.")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()

    report = ExportQualityReport()
    total_rows = 0
    print("Export quality report")
    for filename in args.files:
        path = Path(filename)
        rows = read_jsonl(path, report)
        total_rows += len(rows)
        print(f"{path}: {len(rows)} rows")
        for index, row in enumerate(rows):
            check_row(path, index, row, report)

    print()
    print(f"files: {len(args.files)}")
    print(f"rows: {total_rows}")
    print(f"critical issues: {report.critical_count}")
    print(f"warnings: {report.warning_count}")
    print("result: " + ("FAIL" if report.critical_count else "PASS"))
    return 1 if report.critical_count else 0


class ExportQualityReport:
    def __init__(self) -> None:
        self.critical_count = 0
        self.warning_count = 0

    def critical(self, path: Path, index: int | None, message: str) -> None:
        self.critical_count += 1
        prefix = f"CRITICAL {path}" if index is None else f"CRITICAL {path}:{index}"
        print(f"{prefix}: {message}")

    def warning(self, path: Path, index: int | None, message: str) -> None:
        self.warning_count += 1
        prefix = f"WARNING {path}" if index is None else f"WARNING {path}:{index}"
        print(f"{prefix}: {message}")


def read_jsonl(path: Path, report: ExportQualityReport) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        report.critical(path, None, f"cannot read file: {exc}")
        return rows
    for lineno, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            report.critical(path, lineno, f"invalid JSON: {exc}")
            continue
        if not isinstance(item, dict):
            report.critical(path, lineno, "root JSONL item is not an object")
            continue
        rows.append(item)
    if not rows:
        report.critical(path, None, "file has no JSONL rows")
    return rows


def check_row(path: Path, index: int, row: dict[str, Any], report: ExportQualityReport) -> None:
    train_targets = train_target_texts(row)
    if not train_targets:
        report.critical(path, index, "no assistant train targets found")
        return

    target_text = "\n".join(train_targets)
    full_text = json.dumps(row, ensure_ascii=False, sort_keys=True)
    row_format = str(row.get("format", ""))

    if any(pattern.search(target_text) for pattern in SECRET_PATTERNS):
        report.critical(path, index, "possible API key or bearer token found in assistant train target")
    if any(pattern.search(full_text) for pattern in SECRET_PATTERNS):
        report.critical(path, index, "possible API key or bearer token found in exported row")

    for token in RAW_METADATA_TOKENS:
        if token in target_text:
            report.critical(path, index, f"non-trainable metadata appears in assistant train target: {token}")
        elif token in full_text:
            report.warning(path, index, f"non-trainable metadata appears outside train targets: {token}")

    for marker in REQUIRED_TARGET_MARKERS:
        if marker not in target_text:
            report.critical(path, index, f"assistant target is missing required marker: {marker}")
    if "retry_prompt" not in target_text and "retry_action" not in target_text:
        report.critical(path, index, "assistant target is missing retry decision content")
    if "<submit>" not in target_text and "<discard>" not in target_text:
        report.critical(path, index, "assistant target is missing submit/discard decision")

    if row_format == "qwen_chat":
        check_role_messages(path, index, row.get("messages"), report)
    elif row_format == "trl_conversational":
        check_role_messages(path, index, row.get("messages"), report)
    elif row_format == "sharegpt_llama_factory":
        check_sharegpt(path, index, row, report)
    else:
        report.critical(path, index, f"unsupported or missing export format: {row_format!r}")


def train_target_texts(row: dict[str, Any]) -> list[str]:
    row_format = row.get("format")
    if row_format in {"qwen_chat", "trl_conversational"}:
        messages = row.get("messages")
        if not isinstance(messages, list):
            return []
        return [
            str(message.get("content", ""))
            for message in messages
            if isinstance(message, dict) and message.get("role") == "assistant"
        ]
    if row_format == "sharegpt_llama_factory":
        conversations = row.get("conversations")
        if not isinstance(conversations, list):
            return []
        return [
            str(message.get("value", ""))
            for message in conversations
            if isinstance(message, dict) and message.get("from") == "gpt"
        ]
    return []


def check_role_messages(
    path: Path,
    index: int,
    messages: Any,
    report: ExportQualityReport,
) -> None:
    if not isinstance(messages, list) or not messages:
        report.critical(path, index, "messages must be a non-empty list")
        return
    for msg_index, message in enumerate(messages):
        if not isinstance(message, dict):
            report.critical(path, index, f"messages[{msg_index}] is not an object")
            continue
        if message.get("role") != "assistant":
            report.critical(path, index, f"messages[{msg_index}] is not assistant-only")


def check_sharegpt(path: Path, index: int, row: dict[str, Any], report: ExportQualityReport) -> None:
    conversations = row.get("conversations")
    if not isinstance(conversations, list) or not conversations:
        report.critical(path, index, "conversations must be a non-empty list")
        return
    if row.get("trainable_from") != ["gpt"]:
        report.critical(path, index, "ShareGPT export must mark only gpt messages trainable")
    if not any(isinstance(message, dict) and message.get("from") == "gpt" for message in conversations):
        report.critical(path, index, "ShareGPT export has no gpt train target")


if __name__ == "__main__":
    raise SystemExit(main())
