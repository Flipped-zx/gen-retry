# SFT Data Building

This stage adds a teacher retry-action interface and a dry-run SFT trajectory builder.

No real API key is needed for mock mode. No teacher API call is made when `--dry-run` is set.

## Inputs And Outputs

Default input:

```text
data/raw/geneval_diagnostics.jsonl
```

Teacher retry-action output:

```text
data/processed/teacher_retry_actions.jsonl
```

SFT trajectory output:

```text
data/processed/geneval_retry_sft.jsonl
```

Invalid teacher outputs:

```text
data/failed/invalid_teacher_outputs.jsonl
```

## Teacher Retry Action Schema

The teacher must return one strict JSON object with exactly these keys:

```json
{
  "decision": "retry",
  "failure_types": [],
  "skills_to_call": [],
  "preserve_constraints": [],
  "repair_constraints": [],
  "repair_strategy": "",
  "retry_prompt": "",
  "expected_improvement": [],
  "regression_risks": []
}
```

Rules enforced by `src/gen_retry/teacher/schemas.py`:

- `decision` must be `retry`, `submit`, or `discard`.
- All list fields must be arrays of strings.
- `skills_to_call` must use known Geneval retry skill names.
- No extra keys are allowed.
- `retry` decisions require at least one skill, one repair constraint, and a non-empty retry prompt.
- `submit` decisions cannot include repair constraints.

The JSON schema is also recorded in `schemas/teacher_retry_action.schema.json`.

## Mock Teacher Run

Run from the repository root:

```bash
python3 scripts/build_teacher_retry_actions.py \
  --dry-run \
  --input examples/geneval_diagnostic_example.json \
  --output data/processed/teacher_retry_actions.jsonl \
  --failed-output data/failed/invalid_teacher_outputs.jsonl

python3 scripts/build_sft_trajectories.py \
  --diagnostics examples/geneval_diagnostic_example.json \
  --teacher-actions data/processed/teacher_retry_actions.jsonl \
  --output data/processed/geneval_retry_sft.jsonl
```

The dry-run action is deterministic. For the included apple example, it routes the count failure to `quantity_counting`, preserves red apples and the blue plate, and produces a targeted retry prompt.

`scripts/build_sft_trajectories.py` emits full mocked retry episodes by default. Use `--trajectory-format compact` or `--compact` only when the older diagnostic-to-action message shape is desired.

Full episodes use compact normalized diagnostics in SFT-facing contexts by default. Raw Geneval detector output is kept only under `raw_detector_outputs`, which is marked non-trainable by `masking_metadata`. Use `--diagnostic-detail raw` only for debugging raw contexts.

## Batch Dry Run

Place Geneval-style records in `data/raw/geneval_diagnostics.jsonl`, one JSON object per line. Each object can be either the diagnostic itself or a wrapper with one of these keys:

- `diagnostic`
- `diagnostic_input`
- `geneval_diagnostic`

Then run:

```bash
python3 scripts/build_teacher_retry_actions.py \
  --dry-run \
  --input data/raw/geneval_diagnostics.jsonl \
  --output data/processed/teacher_retry_actions.jsonl \
  --failed-output data/failed/invalid_teacher_outputs.jsonl

python3 scripts/build_sft_trajectories.py \
  --diagnostics data/raw/geneval_diagnostics.jsonl \
  --teacher-actions data/processed/teacher_retry_actions.jsonl \
  --output data/processed/geneval_retry_sft.jsonl
```

## Real Proxy API Run

Use only in a controlled environment with a real key. Do not commit secrets.

```bash
export GEN_RETRY_TEACHER_BASE_URL="https://your-proxy.example.com/v1"
export GEN_RETRY_TEACHER_API_KEY="your_api_key_here"
export GEN_RETRY_TEACHER_MODEL="gpt-5.5"
export GEN_RETRY_TEACHER_TIMEOUT="120"
export GEN_RETRY_TEACHER_MAX_RETRIES="3"

python3 scripts/build_teacher_retry_actions.py \
  --input data/raw/geneval_diagnostics.jsonl \
  --output data/processed/teacher_retry_actions.jsonl \
  --failed-output data/failed/invalid_teacher_outputs.jsonl
```

The client first tries an OpenAI-compatible Responses API path at `/responses`. If that fails because the proxy does not support it, the client falls back to `/chat/completions`.

## SFT Output Shape

`scripts/build_sft_trajectories.py` emits JSONL rows with:

- `id`
- `trajectory_format`
- `masking_metadata`
- `assistant_trainable_messages`
- `tool_observations`
- `raw_detector_outputs`
- `non_trainable_context`
- `messages`
- `episode_steps`
- `images`
- `diagnostic`
- `normalized_diagnostic`
- `teacher_retry_action`
- `mock_retry_diagnostic`
- `outcome`

In the default full episode format, the `messages` field is ShareGPT-style and teaches this mocked chain:

- a system instruction for the Gen-Retry student
- parse constraints
- mock `generate_image` for the first attempt
- mock `judge_image` for the first attempt
- receive and normalize the Geneval diagnostic
- `query_skill`
- repair prompt / retry action
- mock `generate_image` for the retry attempt
- mock `judge_image` for the retry attempt
- submit if the mocked retry judge reports no regression

Masking policy:

- Train only `assistant_trainable_messages`.
- Train assistant diagnostic summaries, tool calls, repair prompts, retry decisions, and submit/discard decisions.
- Do not train on `tool_observations`.
- Do not train on `raw_detector_outputs`.
- Do not train on generated image metadata in `non_trainable_context`.
- Use compact diagnostics in SFT contexts unless raw diagnostic detail is explicitly requested.

The compact format keeps the earlier diagnostic-to-action shape:

```bash
python3 scripts/build_sft_trajectories.py \
  --trajectory-format compact \
  --diagnostics data/raw/geneval_diagnostics.jsonl \
  --teacher-actions data/processed/teacher_retry_actions.jsonl \
  --output data/processed/geneval_retry_sft_compact.jsonl
```

Real image generation, actual retry execution, and real re-evaluation are intentionally out of scope for this stage.
