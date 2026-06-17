"""Stdlib-only validation for Gen-Retry trajectory examples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from gen_retry.data.trajectory import ALLOWED_ROLES, ALLOWED_STEP_TYPES


REQUIRED_TOP_LEVEL = {
    "schema_version",
    "trajectory_id",
    "source_prompt",
    "diagnostic_input",
    "normalized_diagnostic",
    "steps",
    "outcome",
}

REQUIRED_NORMALIZED = {
    "passed_constraints",
    "failed_constraints",
    "failure_types",
    "preserve_candidates",
    "repair_targets",
}


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_trajectory_object(obj: Any) -> list[str]:
    """Return validation errors. An empty list means the object is valid."""

    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["trajectory root must be an object"]

    missing = sorted(REQUIRED_TOP_LEVEL.difference(obj))
    if missing:
        errors.append(f"missing top-level fields: {', '.join(missing)}")

    for key in ("schema_version", "trajectory_id", "source_prompt"):
        if key in obj and not _is_nonempty_string(obj[key]):
            errors.append(f"{key} must be a non-empty string")

    diagnostic_input = obj.get("diagnostic_input")
    if "diagnostic_input" in obj and not isinstance(diagnostic_input, dict):
        errors.append("diagnostic_input must be an object")

    normalized = obj.get("normalized_diagnostic")
    if isinstance(normalized, dict):
        missing_normalized = sorted(REQUIRED_NORMALIZED.difference(normalized))
        if missing_normalized:
            errors.append(
                "normalized_diagnostic missing fields: "
                + ", ".join(missing_normalized)
            )
        for key in REQUIRED_NORMALIZED:
            if key in normalized and not isinstance(normalized[key], list):
                errors.append(f"normalized_diagnostic.{key} must be a list")
    elif "normalized_diagnostic" in obj:
        errors.append("normalized_diagnostic must be an object")

    steps = obj.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty list")
    else:
        for index, step in enumerate(steps):
            label = f"steps[{index}]"
            if not isinstance(step, dict):
                errors.append(f"{label} must be an object")
                continue
            step_type = step.get("type")
            role = step.get("role")
            content = step.get("content")
            if step_type not in ALLOWED_STEP_TYPES:
                errors.append(f"{label}.type is invalid: {step_type!r}")
            if role not in ALLOWED_ROLES:
                errors.append(f"{label}.role is invalid: {role!r}")
            if not _is_nonempty_string(content):
                errors.append(f"{label}.content must be a non-empty string")
            if step_type == "tool_call" and not step.get("tool_name"):
                errors.append(f"{label}.tool_name is required for tool_call")

    outcome = obj.get("outcome")
    if isinstance(outcome, dict):
        if "submitted" in outcome and not isinstance(outcome["submitted"], bool):
            errors.append("outcome.submitted must be a boolean")
        if not _is_nonempty_string(outcome.get("final_status")):
            errors.append("outcome.final_status must be a non-empty string")
    elif "outcome" in obj:
        errors.append("outcome must be an object")

    return errors


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Gen-Retry trajectory JSON file.")
    parser.add_argument("path", help="Path to a trajectory JSON file.")
    args = parser.parse_args()

    path = Path(args.path)
    obj = load_json(path)
    errors = validate_trajectory_object(obj)
    if errors:
        for error in errors:
            print(f"[trajectory error] {error}")
        return 1
    print(f"trajectory valid: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
