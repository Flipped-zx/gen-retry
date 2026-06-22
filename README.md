# Gen-Retry

Diagnostic-conditioned retry scaffolding for agentic image generation.

This repository is currently limited to safe local scaffolding:

- Stage 1: persistent source digests for `../GenEvolve`, `../Gen-Searcher`, and `../GenEval`.
- Stage 2: a stdlib-only Python skeleton for Geneval-style diagnostics, skills, schemas, examples, and safe validation.
- Visual retry collector scaffold: mock generation, mock Geneval-style evaluation, mock teacher actions, raw episode saving, validation, and policy-only SFT export.

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

This is not a generic prompt rewriting project. The mock collector focuses on the Geneval retry surface and keeps real image generation, real Geneval evaluation, training, and RL behind explicit future integration points.

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
  collectors/
  data/
  eval/
  evaluators/
  export/
  filters/
  generators/
  schemas/
  teachers/
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

## Mock Visual Retry Collector

Mock mode requires no API key and calls no external service.

Collect five mock episodes:

```bash
python3 scripts/collect_mock_episodes.py --num 5
```

Validate saved episodes:

```bash
python3 scripts/validate_episodes.py data/raw_episodes
```

Export policy-only SFT rows:

```bash
python3 scripts/export_policy_sft.py
```

Default paths:

```text
data/prompts/sample_prompts.jsonl
data/raw_episodes/
data/images/
data/sft/retry_policy_sft_sharegpt.jsonl
```

The collector loop is:

```text
original prompt
-> mock initial generation
-> mock Geneval-style evaluation
-> mock teacher chooses retry action
-> mock retry executor writes an edited placeholder image
-> mock evaluator evaluates again
-> repeat until pass threshold or retry budget is exhausted
-> save full episode JSON
-> export policy-only SFT as state_t -> action_t
```

The evaluator, not the teacher, decides whether the retry succeeded.

## Qwen-Image + Geneval Batch Diagnostics

For the first real data pass, generate multiple Qwen-Image candidates per prompt, run Geneval externally, and save teacher-ready diagnostics.

Plan 10 prompts x 4 candidates without running any real model:

```bash
python3 scripts/collect_qwen_geneval_diagnostics.py \
  --prompts data/prompts/geneval_pilot_10.jsonl \
  --output-dir data/runs/qwen_geneval_pilot_10 \
  --images-per-prompt 4 \
  --gpus 0,1,2,3 \
  --qwen-model-path /home/develop/biocloudplantform/xxr/models/Qwen-Image-2512 \
  --plan-only
```

In a prepared A100 environment, pass command templates for your actual Qwen-Image and Geneval scripts:

```bash
python3 scripts/collect_qwen_geneval_diagnostics.py \
  --prompts data/prompts/geneval_pilot_10.jsonl \
  --output-dir data/runs/qwen_geneval_pilot_10 \
  --images-per-prompt 4 \
  --gpus 0,1,2,3 \
  --qwen-model-path /home/develop/biocloudplantform/xxr/models/Qwen-Image-2512 \
  --generation-command-template 'python /path/to/qwen_generate.py --model {qwen_model_path} --prompt {prompt} --seed {seed} --out {image_path}' \
  --geneval-command-template 'python /path/to/run_geneval.py --prompt {prompt} --image {image_path} --out {geneval_output_path}'
```

The script saves:

```text
generation_manifest.jsonl
candidate_diagnostics.jsonl
teacher_diagnostics.jsonl
```

Use `teacher_diagnostics.jsonl` later for GPT teacher action GT construction. See `docs/QWEN_GENEVAL_BATCH.md`.

## Real Environment Integration Points

The real adapters are scaffolded but not used in tests:

- `src/gen_retry/teachers/gpt55_teacher_adapter.py`
- `src/gen_retry/generators/qwen_image_edit_adapter.py`

Teacher environment variables:

```bash
GEN_RETRY_TEACHER_BASE_URL=https://your-proxy.example.com/v1
GEN_RETRY_TEACHER_API_KEY=your_api_key_here
GEN_RETRY_TEACHER_MODEL=gpt-5.5
```

Qwen-Image-Edit environment variables:

```bash
GEN_RETRY_QWEN_IMAGE_EDIT_ENDPOINT=https://your-image-edit-endpoint.example.com
GEN_RETRY_QWEN_IMAGE_EDIT_API_KEY=your_api_key_here
```

Do not hard-code API keys. The GPT-5.5 teacher should only choose the next action. It must not decide whether a retry succeeded; success must come from the evaluator.

To replace mocks later:

- replace `MockGenevalEvaluator` with a real Geneval evaluator adapter that returns `NormalizedGenevalReport`;
- replace `MockRetryExecutor` with `QwenImageEditAdapter` or another image edit executor;
- replace `MockTeacher` with `GPT55TeacherAdapter` after wiring the real API call in a controlled environment.

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

Mock teacher action generation is implemented for local collection. The real GPT-5.5 API call is scaffolded but intentionally not implemented for local tests. The placeholder configuration is present for a future OpenAI-compatible relay:

```bash
GEN_RETRY_TEACHER_BASE_URL=https://your-proxy.example.com/v1
GEN_RETRY_TEACHER_API_KEY=your_api_key_here
GEN_RETRY_TEACHER_MODEL=gpt-5.5
GEN_RETRY_TEACHER_TIMEOUT=120
GEN_RETRY_TEACHER_MAX_RETRIES=3
```

Do not hard-code API keys.
