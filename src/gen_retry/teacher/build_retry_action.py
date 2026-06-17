"""Build teacher retry actions from Geneval diagnostics."""

from __future__ import annotations

from typing import Any

from gen_retry.eval.diagnostic_normalizer import normalize_geneval_diagnostic
from gen_retry.teacher.schemas import TeacherRetryAction, validate_teacher_retry_action
from gen_retry.tools.skills import skill_for_failure_type


def extract_diagnostic(record: dict[str, Any]) -> dict[str, Any]:
    """Extract a diagnostic object from a raw input record."""

    for key in ("diagnostic", "diagnostic_input", "geneval_diagnostic"):
        value = record.get(key)
        if isinstance(value, dict):
            return value
    return record


def record_id(record: dict[str, Any], index: int) -> str:
    for key in ("id", "sample_id", "trajectory_id"):
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return f"sample_{index:06d}"


def first_attempt_prompt(record: dict[str, Any], diagnostic: dict[str, Any]) -> str:
    for key in ("first_attempt_prompt", "attempt_prompt", "source_prompt", "prompt"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(diagnostic.get("prompt", "")).strip()


def build_mock_retry_action(
    diagnostic: dict[str, Any],
    *,
    normalized_diagnostic: dict[str, Any] | None = None,
    first_attempt: str | None = None,
) -> TeacherRetryAction:
    """Build a deterministic dry-run action without calling an API."""

    normalized = normalized_diagnostic or normalize_geneval_diagnostic(diagnostic)
    failed = list(normalized.get("failed_constraints") or [])
    failure_types = list(normalized.get("failure_types") or [])
    repair_targets = list(normalized.get("repair_targets") or [])
    preserve_candidates = list(normalized.get("preserve_candidates") or [])

    preserve_constraints = [_format_preserve(candidate) for candidate in preserve_candidates]
    repair_constraints = [_format_repair(item) for item in failed]

    if not failed and not failure_types:
        payload = {
            "decision": "submit",
            "failure_types": [],
            "skills_to_call": [],
            "preserve_constraints": preserve_constraints,
            "repair_constraints": [],
            "repair_strategy": "All tracked constraints passed; submit the current candidate.",
            "retry_prompt": "",
            "expected_improvement": ["No retry is needed because the diagnostic passed."],
            "regression_risks": [],
        }
        return validate_teacher_retry_action(payload)

    skills = []
    for target in repair_targets:
        skill = str(target.get("skill", "")).strip()
        if skill and skill not in skills:
            skills.append(skill)
    for failure_type in failure_types:
        skill = skill_for_failure_type(str(failure_type)).name
        if skill and skill not in skills:
            skills.append(skill)

    if not skills:
        payload = {
            "decision": "discard",
            "failure_types": [str(item) for item in failure_types],
            "skills_to_call": [],
            "preserve_constraints": preserve_constraints,
            "repair_constraints": repair_constraints,
            "repair_strategy": "No reliable repair skill was found for the diagnostic.",
            "retry_prompt": "",
            "expected_improvement": [],
            "regression_risks": ["The failure cannot be repaired with the current skill set."],
        }
        return validate_teacher_retry_action(payload)

    retry_prompt = _build_retry_prompt(
        first_attempt or str(diagnostic.get("prompt", "")),
        preserve_constraints,
        repair_constraints,
    )
    payload = {
        "decision": "retry",
        "failure_types": [str(item) for item in failure_types],
        "skills_to_call": skills,
        "preserve_constraints": preserve_constraints,
        "repair_constraints": repair_constraints,
        "repair_strategy": _build_repair_strategy(skills, preserve_constraints, repair_constraints),
        "retry_prompt": retry_prompt,
        "expected_improvement": [
            "The retry should satisfy failed Geneval checks while keeping passed constraints unchanged."
        ],
        "regression_risks": [
            "Changing the prompt could regress object presence, color binding, or layout constraints that already passed."
        ],
    }
    return validate_teacher_retry_action(payload)


def build_teacher_action_row(
    record: dict[str, Any],
    *,
    index: int,
    dry_run: bool,
    client: Any | None = None,
) -> dict[str, Any]:
    """Build one output row from one diagnostic record."""

    diagnostic = extract_diagnostic(record)
    normalized = normalize_geneval_diagnostic(diagnostic)
    attempt_prompt = first_attempt_prompt(record, diagnostic)
    if dry_run:
        action = build_mock_retry_action(
            diagnostic,
            normalized_diagnostic=normalized,
            first_attempt=attempt_prompt,
        )
        mode = "dry_run"
    else:
        if client is None:
            raise ValueError("client is required when dry_run is false")
        action = client.generate_retry_action(
            diagnostic=diagnostic,
            normalized_diagnostic=normalized,
            first_attempt_prompt=attempt_prompt,
        )
        mode = "api"

    return {
        "id": record_id(record, index),
        "teacher_mode": mode,
        "diagnostic": diagnostic,
        "normalized_diagnostic": normalized,
        "teacher_retry_action": action.to_dict(),
    }


def _format_preserve(candidate: dict[str, Any]) -> str:
    target = candidate.get("target", "constraint")
    prop = candidate.get("property", "value")
    value = candidate.get("value")
    if prop == "presence":
        return f"Keep {target} present."
    return f"Keep {target} {prop} as {value}."


def _format_repair(failed: dict[str, Any]) -> str:
    kind = failed.get("type", "constraint")
    target = failed.get("target", "target")
    expected = failed.get("expected")
    detected = failed.get("detected")
    if kind == "counting":
        return f"Render exactly {expected} {target}; diagnostic detected {detected}."
    if kind == "color_binding":
        return f"Bind {target} to expected color or attribute {expected}."
    if kind == "object_presence":
        return f"Make required {target} clearly visible."
    return f"Repair {kind} for {target}."


def _build_repair_strategy(skills: list[str], preserve: list[str], repair: list[str]) -> str:
    preserve_text = " ".join(preserve) if preserve else "Preserve all constraints that passed."
    repair_text = " ".join(repair) if repair else "Repair the failed diagnostic constraints."
    return f"Call {', '.join(skills)}. {preserve_text} {repair_text}"


def _build_retry_prompt(base_prompt: str, preserve: list[str], repair: list[str]) -> str:
    parts = [base_prompt.strip() or "Generate the requested image."]
    if repair:
        parts.append("Repair: " + " ".join(repair))
    if preserve:
        parts.append("Preserve: " + " ".join(preserve))
    return " ".join(parts)
