# GenEval2 Retry SFT Goal

## Objective

Build high-quality diagnostic-conditioned retry trajectories for agentic image generation.

The quality floor is the earlier 20-prompt hard mining run. New SFT trajectories must be at least as good as those accepted high-quality examples. Do not trade trajectory quality for volume.

The student should learn:

```text
original prompt
-> teacher initial_plan
-> generate image
-> GenEval2 diagnosis
-> identify failed constraints
-> preserve correct constraints
-> teacher retry_replan
-> retry generation
-> re-evaluate
-> accept improved trajectory or reject regressed trajectory
```

This is not generic prompt rewriting. The target behavior is verifier-guided repair.

## Current Pilot

- Prompt set: `data/prompts/geneval2_balanced_100.jsonl`
- Real initial plans: `data/plans/initial/geneval2_balanced_100_gpt55/`
- Initial image target: 100 prompts x 5 candidates = 500 images.
- Generator model: local `../models/Qwen-Image-2512`.
- Evaluator: GenEval2 with original prompt / metadata as the ground-truth constraint source.
- Teacher: `gpt-5.5` through the OpenAI-compatible relay.

## Canonical Pipeline

1. Load one prompt row and its cached `initial_plan`.
2. Generate the first image from `initial_plan.initial_prompt`.
3. Evaluate the image with GenEval2 against the original prompt metadata, not the rewritten generation prompt.
4. If the image passes, export a positive `initial_plan -> submit` trajectory.
5. If the image fails, pass normalized GenEval2 diagnosis plus previous plan/state to teacher `retry_replan`.
6. Generate retry image from `retry_replan.retry_prompt`.
7. Re-run GenEval2.
8. Keep positive retries only when they pass or clearly improve without regression.
9. Send regressed or invalid retry spans to rejected/analysis outputs, not ordinary positive SFT.

## Data Quality Rules

- Never train on raw detector dumps as assistant targets.
- Keep tool/evaluator observations non-trainable unless explicitly converted into assistant reasoning.
- Preserve already-correct constraints in retry prompts.
- Repair only diagnosed failures; do not invent new objects, counts, attributes, or relations.
- Use original GenEval2 prompt metadata for evaluation.
- Reject direct image-edit fields such as masks, bounding boxes, inpainting, or source-image edits.
- Track `branch_source`, score deltas, fixed failures, persistent failures, new failures, and regressed constraints.

## Quality Floor

Use the earlier 20-prompt hard run as the minimum accepted standard.

Accept a trajectory only if:

- the teacher action is schema-valid and uses only allowed skills;
- `initial_plan` or `retry_replan` preserves all explicit original constraints;
- GenEval2 diagnosis is the reason for the retry decision, not a generic rewrite trigger;
- failed constraints are named concretely, including count, object, attribute, relation, or visibility failures;
- already-correct constraints are listed as preserved and remain present in the retry prompt;
- the retry prompt is surgical: it strengthens failed constraints without adding unrelated objects or relations;
- the retry result passes or clearly improves without introducing regression;
- regressed retry spans are routed to rejected/analysis outputs;
- assistant train targets contain no raw detector dumps, local image paths, API logs, or direct-edit instructions.

Batch success is measured by accepted trajectory quality first, then count. If a 100-prompt run produces many low-quality or regressed retries, the correct action is to filter or reject them, not to include them for SFT.

## Qwen-Image Settings

Current `gen-retry` text-to-image pilot defaults:

```text
model_path: ../models/Qwen-Image-2512
n_samples: 5
seed: 1000 + prompt_index * n_samples + candidate_index
width: 1664
height: 928
steps: 50
true_cfg_scale: 4.0
negative_prompt: " "
positive_suffix: ""
workers_per_gpu: 1
```

Recommended 4-GPU initial generation shape:

```bash
python3 scripts/generate_qwen_geneval_images.py \
  --metadata data/prompts/geneval2_balanced_100.jsonl \
  --output-dir data/qwen_geneval2_balanced_100_x5_images \
  --model-path ../models/Qwen-Image-2512 \
  --n-samples 5 \
  --limit 100 \
  --seed 1000 \
  --gpus 0,1,2,3 \
  --workers-per-gpu 1 \
  --dtype bfloat16 \
  --width 1664 \
  --height 928 \
  --steps 50 \
  --true-cfg-scale 4.0 \
  --negative-prompt ' ' \
  --resume \
  --skip-grid \
  --progress-interval 60
```

Important implementation note:

- The current script reads `metadata.prompt`.
- For plan-conditioned initial generation, add `--initial-plan-dir data/plans/initial/geneval2_balanced_100_gpt55` or prepare a derived metadata file whose generation prompt is `initial_plan.initial_prompt` while retaining the original prompt metadata for GenEval2.

## Gen-Searcher Reference Finding

Gen-Searcher contains a Qwen image edit service, not the exact text-to-image pilot path:

- Service file: `Gen-Searcher/qwen_image_api_server/qwen-image-edit/api.py`
- Pipeline: `QwenImageEditPlusPipeline`
- Server shape: one loaded pipeline per GPU, lock-protected scheduling, timeout/reload recovery.
- Run script: `Gen-Searcher/qwen_image_api_server/run_server.bash` starts 8 GPUs on port 8001.
- Request defaults:
  - `true_cfg_scale: 4.0`
  - `negative_prompt: " "`
  - `num_inference_steps: 40`
  - `guidance_scale: 1.0`
  - `num_images_per_prompt: 1`
- RL workflow uses up to 3 reference images for Qwen Edit generation.

This reference supports operational choices like per-GPU serialization and queue limits, but it should not replace the current local Qwen-Image-2512 text-to-image path.

## Completion Criteria

A pilot batch is useful for SFT only when it yields:

- valid initial-plan trajectories for all generated prompts;
- GenEval2 reports for all generated images;
- retry replans only for failed attempts;
- positive retry examples that pass or improve;
- rejected records for regressed retry spans;
- compact/tool SFT exports with raw evaluator outputs masked from assistant targets.
