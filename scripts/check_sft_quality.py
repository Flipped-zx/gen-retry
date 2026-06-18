#!/usr/bin/env python3
"""Stdlib-only quality checks for Gen-Retry SFT JSONL files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROUTING = {
    "count_mismatch": "quantity_counting",
    "counting": "quantity_counting",
    "missing_instance": "quantity_counting",
    "extra_instance": "quantity_counting",
    "missing_object": "object_presence",
    "forbidden_object_present": "object_presence",
    "object_presence": "object_presence",
    "color_mismatch": "attribute_binding",
    "attribute_binding": "attribute_binding",
    "attribute_mismatch": "attribute_binding",
    "color_binding": "attribute_binding",
    "spatial_mismatch": "spatial_layout",
    "spatial_relation": "spatial_layout",
    "visibility_issue": "visibility_and_anti_occlusion",
    "occlusion": "visibility_and_anti_occlusion",
    "occluded_object": "visibility_and_anti_occlusion",
    "low_visibility": "visibility_and_anti_occlusion",
    "unverifiable_constraint": "visibility_and_anti_occlusion",
}

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(r"(?i)\bapi[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9._-]{16,}"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Gen-Retry SFT trajectory quality.")
    parser.add_argument("--sft", default="data/processed/geneval_retry_sft_5_full.jsonl")
    parser.add_argument("--diagnostics")
    parser.add_argument("--actions")
    args = parser.parse_args()

    report = QualityReport()
    sft_rows = read_jsonl(Path(args.sft), report, label="sft")
    diagnostics = read_jsonl(Path(args.diagnostics), report, label="diagnostics") if args.diagnostics else []
    actions = read_jsonl(Path(args.actions), report, label="actions") if args.actions else []

    if diagnostics and len(diagnostics) != len(sft_rows):
        report.critical(f"diagnostics row count {len(diagnostics)} != sft row count {len(sft_rows)}")
    if actions and len(actions) != len(sft_rows):
        report.critical(f"actions row count {len(actions)} != sft row count {len(sft_rows)}")

    print("SFT quality report")
    print(f"sft: {args.sft}")
    print(f"trajectories: {len(sft_rows)}")
    if diagnostics:
        print(f"diagnostics: {len(diagnostics)}")
    if actions:
        print(f"actions: {len(actions)}")
    print()

    for index, row in enumerate(sft_rows):
        check_row(index, row, actions[index] if index < len(actions) else None, report)

    report.print_summary()
    return 1 if report.critical_count else 0


class QualityReport:
    def __init__(self) -> None:
        self.critical_count = 0
        self.warning_count = 0
        self.row_status: dict[int, list[str]] = {}

    def critical(self, message: str, index: int | None = None) -> None:
        self.critical_count += 1
        prefix = "CRITICAL" if index is None else f"CRITICAL row {index}"
        print(f"{prefix}: {message}")
        if index is not None:
            self.row_status.setdefault(index, []).append("critical")

    def warning(self, message: str, index: int | None = None) -> None:
        self.warning_count += 1
        prefix = "WARNING" if index is None else f"WARNING row {index}"
        print(f"{prefix}: {message}")
        if index is not None:
            self.row_status.setdefault(index, []).append("warning")

    def pass_row(self, index: int, prompt: str) -> None:
        flags = self.row_status.get(index, [])
        status = "PASS" if not flags else "PASS_WITH_WARNINGS" if "critical" not in flags else "FAIL"
        print(f"{status} row {index}: {prompt}")

    def print_summary(self) -> None:
        print()
        print(f"critical issues: {self.critical_count}")
        print(f"warnings: {self.warning_count}")
        print("result: " + ("FAIL" if self.critical_count else "PASS"))


def read_jsonl(path: Path, report: QualityReport, *, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        report.critical(f"cannot read {label} file {path}: {exc}")
        return rows
    for lineno, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            report.critical(f"{label}:{lineno} is not valid JSON: {exc}")
            continue
        if not isinstance(item, dict):
            report.critical(f"{label}:{lineno} root is not an object")
            continue
        rows.append(item)
    return rows


def check_row(
    index: int,
    row: dict[str, Any],
    action_row: dict[str, Any] | None,
    report: QualityReport,
) -> None:
    prompt = str((row.get("diagnostic") or {}).get("prompt", row.get("id", "")))
    steps = row.get("episode_steps")
    if not isinstance(steps, list):
        report.critical("missing episode_steps list", index)
        steps = []
    step_types = [str(step.get("type", "")) for step in steps if isinstance(step, dict)]
    tool_names = [str(step.get("tool_name", "")) for step in steps if isinstance(step, dict)]

    if "parse_constraints" not in step_types:
        report.critical("missing parse_constraints step", index)
    if count_tool_or_step(step_types, tool_names, "generate_image") < 2:
        report.critical("generate_image must appear at least twice", index)
    if count_tool_or_step(step_types, tool_names, "judge_image") < 1:
        report.critical("judge_image must appear at least once", index)
    if "receive_geneval_diagnostic" not in step_types:
        report.critical("missing receive_geneval_diagnostic step", index)
    if "query_skill" not in step_types and "query_skill" not in tool_names:
        report.critical("missing query_skill step/tool", index)
    if "repair_prompt" not in step_types and "retry_action" not in step_types:
        report.critical("missing repair_prompt or retry_action step", index)
    if not ({"submit", "discard"} & set(step_types)):
        report.critical("missing submit or discard decision", index)

    action = row.get("teacher_retry_action")
    if not isinstance(action, dict):
        report.critical("missing teacher_retry_action object", index)
        action = {}
    failure_types = list_strings(action.get("failure_types"))
    skills = list_strings(action.get("skills_to_call"))
    for failure_type in failure_types:
        expected_skill = ROUTING.get(failure_type)
        if expected_skill and expected_skill not in skills:
            report.critical(
                f"failure type {failure_type!r} should route to {expected_skill!r}, got {skills}",
                index,
            )

    if not list_strings(action.get("preserve_constraints")):
        report.critical("preserve_constraints is missing or empty", index)
    if action.get("decision") == "retry":
        if not list_strings(action.get("repair_constraints")):
            report.critical("repair_constraints is missing or empty for retry", index)
        if not str(action.get("retry_prompt", "")).strip():
            report.critical("retry_prompt is missing for retry", index)

    normalized = row.get("normalized_diagnostic")
    if not isinstance(normalized, dict):
        report.critical("missing normalized_diagnostic object", index)
        normalized = {}
    if has_spatial_failure(row, failure_types):
        failed = normalized.get("failed_constraints")
        repairs = normalized.get("repair_targets")
        if not nonempty_list(failed) and not nonempty_list(repairs):
            report.critical("spatial failure has empty failed_constraints and repair_targets", index)
        if not has_structured_spatial_detail(failed, repairs):
            report.critical("spatial failure lacks structured spatial_relation/spatial_layout detail", index)

    full_text = json.dumps(row, ensure_ascii=False, sort_keys=True)
    if contains_secret(full_text):
        report.critical("possible API key or bearer token string found", index)

    masking_ok = check_masking_metadata(index, row, report)
    assistant_text = json.dumps(row.get("assistant_trainable_messages", []), ensure_ascii=False, sort_keys=True)
    if contains_detector_metadata(assistant_text):
        report.critical("detector metadata appears in assistant train target", index)
    tool_text = json.dumps(row.get("tool_observations", []), ensure_ascii=False, sort_keys=True)
    if contains_detector_metadata(tool_text):
        if masking_ok:
            report.warning("detector metadata appears in masked tool observations", index)
        else:
            report.critical("detector metadata appears in tool observations without valid masking metadata", index)
    raw_text = json.dumps(row.get("raw_detector_outputs", {}), ensure_ascii=False, sort_keys=True)
    if contains_detector_metadata(raw_text) and not masking_ok:
        report.critical("raw detector outputs exist without valid masking metadata", index)

    if action_row is not None:
        check_source_action_warning(index, row, action_row, report)

    report.pass_row(index, prompt)


def count_tool_or_step(step_types: list[str], tool_names: list[str], name: str) -> int:
    return sum(1 for item in step_types if item == name) + sum(1 for item in tool_names if item == name)


def list_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value)


def has_spatial_failure(row: dict[str, Any], failure_types: list[str]) -> bool:
    if any("spatial" in failure_type for failure_type in failure_types):
        return True
    checks = ((row.get("diagnostic") or {}).get("checks") or {})
    return isinstance(checks, dict) and checks.get("spatial_relation") is False


def has_structured_spatial_detail(failed: Any, repairs: Any) -> bool:
    if isinstance(failed, list):
        for item in failed:
            if isinstance(item, dict) and item.get("type") == "spatial_relation":
                if item.get("subject") and item.get("relation") and item.get("object"):
                    return True
                if item.get("failure_reason"):
                    return True
    if isinstance(repairs, list):
        for item in repairs:
            if isinstance(item, dict) and item.get("skill") == "spatial_layout":
                return True
    return False


def contains_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def contains_detector_metadata(text: str) -> bool:
    return '"bbox"' in text or '"score"' in text


def check_masking_metadata(index: int, row: dict[str, Any], report: QualityReport) -> bool:
    ok = True
    required_fields = (
        "assistant_trainable_messages",
        "tool_observations",
        "raw_detector_outputs",
        "non_trainable_context",
    )
    masking = row.get("masking_metadata")
    if not isinstance(masking, dict):
        report.critical("missing masking_metadata object", index)
        ok = False
    for field in required_fields:
        if field not in row:
            report.critical(f"missing hygiene field: {field}", index)
            ok = False
    if not isinstance(row.get("assistant_trainable_messages"), list):
        report.critical("assistant_trainable_messages must be a list", index)
        ok = False
    if not isinstance(row.get("tool_observations"), list):
        report.critical("tool_observations must be a list", index)
        ok = False
    if not isinstance(row.get("raw_detector_outputs"), dict):
        report.critical("raw_detector_outputs must be an object", index)
        ok = False
    if not isinstance(row.get("non_trainable_context"), dict):
        report.critical("non_trainable_context must be an object", index)
        ok = False
    if isinstance(masking, dict):
        train_on = list_strings(masking.get("train_on"))
        do_not_train_on = list_strings(masking.get("do_not_train_on"))
        required_train = (
            "assistant diagnostic summaries",
            "assistant tool calls",
            "assistant retry decisions",
            "assistant repair prompts",
            "assistant submit/discard decisions",
        )
        required_mask = (
            "raw Geneval detector outputs",
            "tool observations",
            "generated image metadata",
        )
        for item in required_train:
            if item not in train_on:
                report.critical(f"masking_metadata.train_on missing {item!r}", index)
                ok = False
        for item in required_mask:
            if item not in do_not_train_on:
                report.critical(f"masking_metadata.do_not_train_on missing {item!r}", index)
                ok = False
    return ok


def check_source_action_warning(
    index: int,
    row: dict[str, Any],
    action_row: dict[str, Any],
    report: QualityReport,
) -> None:
    action = action_row.get("teacher_retry_action")
    normalized = action_row.get("normalized_diagnostic")
    if not isinstance(action, dict) or not isinstance(normalized, dict):
        return
    failure_types = list_strings(action.get("failure_types"))
    if not any("spatial" in item for item in failure_types):
        return
    if not nonempty_list(normalized.get("failed_constraints")) or not nonempty_list(
        normalized.get("repair_targets")
    ):
        row_normalized = row.get("normalized_diagnostic")
        if isinstance(row_normalized, dict) and has_structured_spatial_detail(
            row_normalized.get("failed_constraints"),
            row_normalized.get("repair_targets"),
        ):
            return
        report.warning(
            "source teacher action row has stale/empty spatial normalized_diagnostic; SFT row should be authoritative",
            index,
        )


if __name__ == "__main__":
    raise SystemExit(main())
