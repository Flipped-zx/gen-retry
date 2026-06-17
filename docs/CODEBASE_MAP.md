# Codebase Map

## Current Repository: `gen-retry`

```text
AGENTS.md
README.md
pyproject.toml
.env.example
configs/
  skills/geneval_skills.yaml
  teacher/teacher_api.example.yaml
docs/
  requests/
  repo_digests/
  CODEBASE_MAP.md
  CODEX_HANDOFF.md
  PROGRESS.md
examples/
  geneval_diagnostic_example.json
  geneval_retry_example.json
schemas/
  sft_trajectory.schema.json
scripts/
  build_sft_trajectories.py
  build_teacher_retry_actions.py
  safe_check.py
src/gen_retry/
  __init__.py
  data/
    __init__.py
    io.py
    trajectory.py
    validate_trajectory.py
  eval/
    __init__.py
    diagnostic_normalizer.py
  teacher/
    __init__.py
    build_retry_action.py
    client.py
    prompts.py
    schemas.py
  tools/
    __init__.py
    registry.py
    skills.py
tests/
  test_diagnostic_normalizer.py
  test_teacher_schema.py
  test_trajectory_schema.py
```

## Read-Only Source Repositories

### `../GenEvolve`

Use for:

- ReAct trajectory convention.
- `search`, `image_search`, `query_knowledge` tool protocol.
- static skill bank pattern.
- final prompt-reference program shape.
- runtime guardrails around final answers and reference-image resolution.

Do not use for:

- direct training script reuse. The public repo does not include full trainer code.
- Geneval diagnostics. It solves grounded prompt-reference generation, not diagnostic-conditioned retry.

### `../Gen-Searcher`

Use for:

- search/image_search/browse workflow.
- multimodal tool observation handling.
- ShareGPT `messages` plus `images` SFT adapter.
- RL `Episode`/`Step` decomposition pattern.
- reward/masking concepts for future stages.

Do not use in Stage 2:

- RL training.
- reward model calls.
- image generation service calls.
- web search tools.

### `../GenEval`

Use for:

- prompt category taxonomy.
- object/count/color/spatial checks.
- result JSONL fields: `correct`, `reason`, `metadata`, `details`.
- per-tag and per-prompt aggregation logic.

Do not run locally in safe mode:

- CUDA evaluator.
- model downloads.
- dependency installs.

## Stage 2 Implementation Boundary

Implemented now:

- static schemas and examples.
- diagnostic normalization for a Geneval-style object.
- tool and skill registries as placeholders.
- stdlib trajectory validation.
- persistent repo digests.
- OpenAI-compatible teacher client interface.
- strict teacher retry-action schema with stdlib validation.
- deterministic dry-run teacher action builder.
- JSONL scripts for teacher retry actions and SFT trajectories.

Not implemented now:

- full retry-loop executor.
- image generation.
- Geneval raw result adapter.
- RL or reward computation.
