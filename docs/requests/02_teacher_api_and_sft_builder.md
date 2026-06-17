# Task: Teacher API and SFT Trajectory Builder

Read first:
- docs/requests/00_project_brief.md
- docs/repo_digests/genevolve_digest.md
- docs/repo_digests/gen_searcher_digest.md
- docs/repo_digests/geneval_digest.md
- docs/CODEBASE_MAP.md
- docs/CODEX_HANDOFF.md

Do not re-scan ../GenEvolve, ../Gen-Searcher, or ../GenEval unless absolutely necessary.

Implement the teacher API and SFT trajectory builder.

## Goal

Use an OpenAI-compatible proxy API to generate teacher retry actions from Geneval diagnostic feedback.

The teacher should receive:

- original prompt
- expected constraints
- first attempt prompt
- Geneval diagnostic JSON
- detected objects / bboxes / colors
- skill library

The teacher should output strict JSON:

{
  "decision": "retry" | "submit" | "discard",
  "failure_types": [],
  "skills_to_call": [],
  "preserve_constraints": [],
  "repair_constraints": [],
  "repair_strategy": "",
  "retry_prompt": "",
  "expected_improvement": [],
  "regression_risks": []
}

## Environment variables

Support proxy API through:

- GEN_RETRY_TEACHER_BASE_URL
- GEN_RETRY_TEACHER_API_KEY
- GEN_RETRY_TEACHER_MODEL
- GEN_RETRY_TEACHER_TIMEOUT
- GEN_RETRY_TEACHER_MAX_RETRIES

Do not hard-code keys.

## Files to create

- src/gen_retry/teacher/__init__.py
- src/gen_retry/teacher/client.py
- src/gen_retry/teacher/prompts.py
- src/gen_retry/teacher/schemas.py
- src/gen_retry/teacher/build_retry_action.py
- scripts/build_teacher_retry_actions.py
- scripts/build_sft_trajectories.py
- tests/test_teacher_schema.py

## Client requirements

Use a clean OpenAI-compatible client.

The client should allow:

base_url = os.environ["GEN_RETRY_TEACHER_BASE_URL"]
api_key = os.environ["GEN_RETRY_TEACHER_API_KEY"]
model = os.environ.get("GEN_RETRY_TEACHER_MODEL", "gpt-5.5")

The code should support both:
- official OpenAI API
- relay/proxy API with OpenAI-compatible base_url

If the model does not support the Responses API through the proxy, add a fallback Chat Completions path.

## Data requirements

Input JSONL:
data/raw/geneval_diagnostics.jsonl

Output JSONL:
data/processed/teacher_retry_actions.jsonl
data/processed/geneval_retry_sft.jsonl

## Validation

Validate every teacher output with Pydantic.
Invalid outputs should be retried or saved to:
data/failed/invalid_teacher_outputs.jsonl

## Stop condition

Stop after a local dry run works using examples/geneval_diagnostic_example.json without requiring a real API key.

Also document how to run with a real proxy API key in docs/SFT_DATA_BUILDING.md.
