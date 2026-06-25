# Gen-Retry

Gen-Retry is a Geneval/Geneval2-guided re-planning agent for image generation.
The generator is a frozen prompt-to-image executor. The evaluator is a frozen
Geneval/Geneval2 verifier. The trainable target is the planner/controller that
learns macro actions for initial planning and verifier-guided retry planning.

This version does not use direct image edit. A retry means re-planning a better
prompt and regenerating a fresh image.

The supervised macro actions are:

- `initial_plan`: parse constraints, select fixed skills, build the first generation strategy, and produce `initial_prompt`.
- `retry_replan`: read normalized verifier feedback, diagnose failures, revise skills, and produce a new `retry_prompt` for regeneration.

Stop decisions are rule-based by default and are saved for analysis, but they
are not exported as SFT targets by default. Future RL can optimize the same
planner with Geneval/Geneval2 before-after reward.

The default loop is:

```text
prompt
-> teacher.initial_plan
-> generator.generate(initial_prompt)
-> evaluator.evaluate(image)
-> if not passed: teacher.retry_replan
-> generator.generate(retry_prompt)
-> evaluator.evaluate(image)
-> repeat until rule-based stop
-> save full episode
-> export SFT data
```

The fixed skill library is:

```text
object_presence
quantity_counting
attribute_binding
spatial_layout
anti_occlusion
multi_object_composition
clarity_visibility
negative_constraints
```

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
  prompts/
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

## Mock Episode Collector

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
python3 scripts/export_sft.py --input data/raw_episodes --output data/sft/retry_sft.jsonl
```

Default paths:

```text
data/prompts/sample_prompts.jsonl
data/raw_episodes/
data/images/
data/sft/retry_sft.jsonl
data/rejected/retry_replan_rejected.jsonl
```

The collector loop is:

```text
original prompt
-> mock teacher creates initial_plan
-> mock generator writes a generated placeholder image
-> mock Geneval-style evaluator returns a normalized report
-> mock teacher creates retry_replan when constraints fail
-> mock generator regenerates from retry_prompt
-> mock evaluator evaluates again
-> repeat until pass threshold or retry budget is exhausted
-> save full episode JSON
-> export ShareGPT SFT for initial_plan and retry_replan
```

The evaluator, not the teacher, decides whether the retry succeeded.

Default stop rules:

- stop if `failed_constraints` is empty;
- stop if `score >= 0.95` and no critical failure exists;
- stop if `retry_round >= max_retry`;
- otherwise continue.

Default SFT export does not train on image paths, raw Geneval outputs, detector
boxes, tool observations, generator metadata, API logs, or stop decisions.

## Qwen-Image + Geneval Batch Diagnostics

For the first real data pass, generate multiple Qwen-Image candidates per prompt, run Geneval externally, and save teacher-ready diagnostics.

If you want the official GenEval loop directly inside `gen-retry`, use the two-step path below. It generates 4 Qwen-Image candidates per prompt in the official GenEval image layout, runs `geneval/evaluation/evaluate_images.py`, computes prompt-level scores over the 4 candidates, and writes GPT-teacher-ready rows for selected failed candidates.

Generate 10 prompts x 4 candidates:

```bash
python3 scripts/generate_qwen_geneval_images.py \
  --metadata ../geneval/prompts/evaluation_metadata.jsonl \
  --output-dir data/runs/qwen_geneval_official_10/images_geneval \
  --model-path /home/develop/biocloudplantform/xxr/models/Qwen-Image-2512 \
  --n-samples 4 \
  --limit 10 \
  --gpus 0,1,2,3 \
  --resume
```

Run official GenEval and select prompts whose 4-image pass rate is in a target range, for example `[0.25, 0.75]`:

```bash
python3 scripts/run_geneval_select_teacher_diagnostics.py \
  --image-dir data/runs/qwen_geneval_official_10/images_geneval \
  --geneval-dir ../geneval \
  --object-detector-path /path/to/geneval/object_detector \
  --output-dir data/runs/qwen_geneval_official_10/selected \
  --min-prompt-score 0.25 \
  --max-prompt-score 0.75 \
  --candidate-policy failed
```

Then call the GPT teacher on the selected diagnostics:

```bash
python3 scripts/build_teacher_retry_actions.py \
  --input data/runs/qwen_geneval_official_10/selected/teacher_diagnostics.selected.jsonl \
  --output data/processed/teacher_retry_actions_geneval_official_10.jsonl \
  --failed-output data/failed/teacher_retry_actions_geneval_official_10_failed.jsonl
```

The prompt-level score is the fraction of the 4 candidates that passed official GenEval. With 4 candidates, possible values are `0.0`, `0.25`, `0.5`, `0.75`, and `1.0`. For retry data, `--candidate-policy failed` keeps only failed candidates from selected prompts, because passing candidates do not need a retry action.

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

## Normalizing GenEval2 Official Outputs

GenEval2's official `evaluation.py` writes atom-level score lists. Gen-Retry
normalizes those VQA atom scores into `NormalizedEvalReport` rows so the same
`retry_replan` teacher prompt can consume Geneval2 feedback.

If you have the official score list plus GenEval2 benchmark metadata:

```bash
python3 scripts/normalize_geneval2_results.py \
  --input ../GenEval2/outputs/score_lists.json \
  --benchmark-data ../GenEval2/geneval2_data.jsonl \
  --output data/normalized/geneval2_normalized_reports.jsonl \
  --aggregate-by prompt_id
```

The output is JSONL with one row per prompt/image group:

```text
group_id
prompt
image_id
image_path
raw_rows_count
normalized_report
```

`normalized_report` contains `score`, `passed_constraints`,
`failed_constraints`, `uncertain_constraints`, and `critical_failure_types`.
GenEval2 skills are mapped into retry failure types, for example `count` to
`count_mismatch`, color attributes to `color_mismatch`, non-color attributes to
`attribute_mismatch`, `position` to `spatial_mismatch`, and `verb` to
`relation_mismatch`. These normalized reports can be passed into the
re-planning trajectory collector as verifier feedback.

## Real Environment Integration Points

The real adapters are scaffolded but not used in tests:

- `src/gen_retry/teachers/gpt55_teacher_adapter.py`
- `src/gen_retry/teachers/seed_teacher_adapter.py`
- `src/gen_retry/generators/real_generator_adapter.py`
- `src/gen_retry/evaluators/geneval_adapter.py`
- `src/gen_retry/evaluators/geneval2_adapter.py`

Teacher environment variables:

```bash
GEN_RETRY_TEACHER_BASE_URL=https://your-proxy.example.com/v1
GEN_RETRY_TEACHER_API_KEY=your_api_key_here
GEN_RETRY_TEACHER_MODEL=gpt-5.5
```

Do not hard-code API keys. The GPT-5.5/Seed teacher should only choose planner
actions. It must not decide whether a retry succeeded; success must come from
the evaluator.

To replace mocks later:

- replace `MockGenevalEvaluator` with `GenevalAdapter` or `Geneval2Adapter`;
- replace `MockGenerator` with `RealGeneratorAdapter`;
- replace `MockTeacher` with `GPT55TeacherAdapter` or `SeedTeacherAdapter`.

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
