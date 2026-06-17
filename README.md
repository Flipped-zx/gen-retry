# Gen-Retry

Diagnostic-conditioned retry scaffolding for agentic image generation.

This repository is currently limited to Stage 1 and Stage 2:

- Stage 1: persistent source digests for `../GenEvolve`, `../Gen-Searcher`, and `../GenEval`.
- Stage 2: a stdlib-only Python skeleton for Geneval-style diagnostics, skills, schemas, examples, and safe validation.

The target student model is `Qwen3-VL-4B-Instruct`. The intended training behavior is:

```text
original prompt
-> first generation
-> Geneval-style diagnostic feedback
-> identify failed constraints
-> call an appropriate skill
-> preserve already-correct constraints
-> repair only failed targets
-> retry generation
-> re-evaluate
-> submit improved result
```

This is not a generic prompt rewriting project. The first version focuses on the Geneval retry surface, not web search, teacher trajectory generation, RL, or image generation.

## Repository Map

```text
configs/
  skills/geneval_skills.yaml
  teacher/teacher_api.example.yaml
docs/
  CODEBASE_MAP.md
  CODEX_HANDOFF.md
  PROGRESS.md
  repo_digests/
examples/
  geneval_diagnostic_example.json
  geneval_retry_example.json
schemas/
  sft_trajectory.schema.json
scripts/
  safe_check.py
src/gen_retry/
  data/
  eval/
  tools/
tests/
```

## Safe Local Validation

Only stdlib checks are required on this local machine:

```bash
python3 scripts/safe_check.py
python3 -m compileall src scripts tests
python3 -m json.tool examples/geneval_diagnostic_example.json
python3 -m json.tool examples/geneval_retry_example.json
```

Optional stdlib trajectory validation, for a controlled environment:

```bash
PYTHONPATH=src python3 -m gen_retry.data.validate_trajectory examples/geneval_retry_example.json
```

Full pytest-based testing is intentionally not required for this stage.

## Minimal Diagnostic Flow

Input is a Geneval-style diagnostic JSON with:

- `prompt`
- `category`
- `expected`
- `detected`
- `checks`
- `failure_reason`

`src/gen_retry/eval/diagnostic_normalizer.py` converts it into:

- `passed_constraints`
- `failed_constraints`
- `failure_types`
- `preserve_candidates`
- `repair_targets`

The example in `examples/geneval_retry_example.json` shows the intended SFT trajectory:

```text
prompt
-> parse constraints
-> first generation
-> judge diagnostic
-> call quantity_counting
-> preserve red apples and blue plate
-> repair count to exactly three apples
-> retry
-> judge again
-> submit
```

## Teacher API Placeholder

Teacher generation is not implemented in Stage 1 or Stage 2. The placeholder configuration is present for a future OpenAI-compatible relay:

```bash
GEN_RETRY_TEACHER_BASE_URL=https://your-proxy.example.com/v1
GEN_RETRY_TEACHER_API_KEY=your_api_key_here
GEN_RETRY_TEACHER_MODEL=gpt-5.5
GEN_RETRY_TEACHER_TIMEOUT=120
GEN_RETRY_TEACHER_MAX_RETRIES=3
```

Do not hard-code API keys.
