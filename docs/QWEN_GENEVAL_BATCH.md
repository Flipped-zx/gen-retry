# Qwen-Image + Geneval Batch Diagnostics

This scaffold is for the first real data stage:

```text
prompt
-> Qwen-Image generates 4 candidates
-> Geneval evaluates each image
-> Gen-Retry saves structured diagnostics and error reasons
-> GPT teacher can later build retry-action ground truth from teacher_diagnostics.jsonl
```

The local repository does not run Qwen-Image or Geneval by itself. The batch script calls command templates that you provide in a prepared A100 environment.

There are now two supported paths:

- Official GenEval path: `generate_qwen_geneval_images.py` writes the exact official GenEval image layout, then `run_geneval_select_teacher_diagnostics.py` runs `geneval/evaluation/evaluate_images.py`, computes prompt-level scores over 4 candidates, and writes selected teacher diagnostics.
- Command-template path: `collect_qwen_geneval_diagnostics.py` calls your own generation and Geneval wrappers and expects each wrapper to write one structured JSON output per candidate.

Use the official path when your goal is to mine first-batch retry data from the standard GenEval benchmark.

## Official GenEval Path

Generate 4 Qwen-Image candidates per prompt:

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

This writes:

```text
data/runs/qwen_geneval_official_10/images_geneval/
  generation_manifest.jsonl
  00000/
    metadata.jsonl
    grid.png
    samples/
      00000.png
      00001.png
      00002.png
      00003.png
```

## DCU/ROCm Plan-Conditioned Generation

Use `scripts/generate_qwen_geneval_images_dcu.py` on DCU machines where worker visibility should be controlled by `HIP_VISIBLE_DEVICES`. The script still passes `--device cuda:0` to PyTorch because ROCm PyTorch exposes HIP devices through the CUDA API surface.

For the GenEval2 100-prompt pilot, pass `--initial-plan-dir data/plans/initial/geneval2_balanced_100_gpt55` so the first image generation uses the cached teacher `initial_plan.initial_prompt`, while metadata still preserves the original GenEval2 prompt and VQA fields. Use a fresh output directory for this clean plan-conditioned pass; the older `data/qwen_geneval2_balanced_100_x5_images` directory contains a small partial raw-prompt run.

For four physical DCU cards numbered 0-3:

```bash
HIP_VISIBLE_DEVICES=0,1,2,3 python3 scripts/generate_qwen_geneval_images_dcu.py \
  --metadata data/prompts/geneval2_balanced_100.jsonl \
  --initial-plan-dir data/plans/initial/geneval2_balanced_100_gpt55 \
  --output-dir data/qwen_geneval2_balanced_100_x5_initial_gpt55_images \
  --model-path /root/private_data/models/Qwen-Image-2512 \
  --n-samples 5 \
  --limit 100 \
  --gpus 0,1,2,3 \
  --workers-per-gpu 1 \
  --skip-grid \
  --resume
```

If the machine exposes the four target cards as physical IDs 1-4, use `HIP_VISIBLE_DEVICES=1,2,3,4` and keep `--gpus 0,1,2,3`; the `--gpus` values are then logical indexes within the parent HIP mask.

## Six-Card A100 Plan-Conditioned Generation

Use the regular CUDA entrypoint on A100 machines. Keep these runs in fresh output directories because older `data/qwen_geneval2_balanced_100_x5_images` outputs were produced from raw prompts.

Balanced 100 prompts:

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5 python3 scripts/generate_qwen_geneval_images.py \
  --metadata data/prompts/geneval2_balanced_100.jsonl \
  --initial-plan-dir data/plans/initial/geneval2_balanced_100_gpt55 \
  --output-dir data/qwen_geneval2_balanced_100_x5_initial_gpt55_a100 \
  --model-path /root/private_data/models/Qwen-Image-2512 \
  --n-samples 5 \
  --limit 100 \
  --seed 1000 \
  --gpus 0,1,2,3,4,5 \
  --workers-per-gpu 1 \
  --dtype bfloat16 \
  --width 1664 \
  --height 928 \
  --steps 50 \
  --true-cfg-scale 4.0 \
  --negative-prompt ' ' \
  --skip-grid \
  --resume \
  --progress-interval 60
```

Remaining 63 prompts not present in balanced 100:

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5 python3 scripts/generate_qwen_geneval_images.py \
  --metadata data/prompts/geneval2_remaining_after_balanced100.jsonl \
  --initial-plan-dir data/plans/initial/geneval2_remaining_after_balanced100_gpt55 \
  --output-dir data/qwen_geneval2_remaining_after_balanced100_x5_initial_gpt55_a100 \
  --model-path /root/private_data/models/Qwen-Image-2512 \
  --n-samples 5 \
  --limit 63 \
  --seed 1000 \
  --gpus 0,1,2,3,4,5 \
  --workers-per-gpu 1 \
  --dtype bfloat16 \
  --width 1664 \
  --height 928 \
  --steps 50 \
  --true-cfg-scale 4.0 \
  --negative-prompt ' ' \
  --skip-grid \
  --resume \
  --progress-interval 60
```

Run official GenEval and select prompt groups:

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

Outputs:

```text
data/runs/qwen_geneval_official_10/selected/
  geneval_results.jsonl
  candidate_diagnostics.jsonl
  prompt_selection.jsonl
  selected_candidate_diagnostics.jsonl
  teacher_diagnostics.selected.jsonl
```

`prompt_selection.jsonl` contains one row per prompt. `prompt_score` is the fraction of the 4 generated images that passed official GenEval, so the possible values are `0.0`, `0.25`, `0.5`, `0.75`, and `1.0`. A useful first retry-data range is usually `0.25 <= prompt_score <= 0.75`: the prompt is neither trivially solved nor completely broken.

`--candidate-policy failed` sends only failed candidates from selected prompt groups to the GPT teacher. Other options are:

- `all`: send every candidate from selected prompt groups.
- `best_failed`: send the highest-scoring failed candidate per selected prompt.
- `worst_failed`: send the lowest-scoring failed candidate per selected prompt.

Then call the GPT teacher:

```bash
python3 scripts/build_teacher_retry_actions.py \
  --input data/runs/qwen_geneval_official_10/selected/teacher_diagnostics.selected.jsonl \
  --output data/processed/teacher_retry_actions_geneval_official_10.jsonl \
  --failed-output data/failed/teacher_retry_actions_geneval_official_10_failed.jsonl
```

For local validation without API calls, add `--dry-run` to the teacher command.

## Output Layout

For `--output-dir data/runs/qwen_geneval_pilot_10`, the script writes:

```text
data/runs/qwen_geneval_pilot_10/
  generation_manifest.jsonl
  images/
    pilot_000_cand_00.png
    pilot_000_cand_01.png
  geneval_raw/
    pilot_000_cand_00.json
    pilot_000_cand_01.json
  candidate_diagnostics.jsonl
  teacher_diagnostics.jsonl
  generation_failed.jsonl       # only if failures happen
  geneval_failed.jsonl          # only if failures happen
```

`candidate_diagnostics.jsonl` keeps all generation and evaluation metadata.
Each candidate row records the Qwen model path used for generation. The default is:

```text
/home/develop/biocloudplantform/xxr/models/Qwen-Image-2512
```

`teacher_diagnostics.jsonl` is the file to feed into the teacher-action builder later:

```bash
python3 scripts/build_teacher_retry_actions.py \
  --input data/runs/qwen_geneval_pilot_10/teacher_diagnostics.jsonl \
  --output data/processed/teacher_retry_actions_real_10.jsonl \
  --failed-output data/failed/teacher_retry_actions_real_10_failed.jsonl
```

## Plan A Batch

This creates the manifest only:

```bash
python3 scripts/collect_qwen_geneval_diagnostics.py \
  --prompts data/prompts/geneval_pilot_10.jsonl \
  --output-dir data/runs/qwen_geneval_pilot_10 \
  --images-per-prompt 4 \
  --gpus 0,1,2,3 \
  --qwen-model-path /home/develop/biocloudplantform/xxr/models/Qwen-Image-2512 \
  --plan-only
```

For 10 prompts and 4 images per prompt, expected candidates: 40.

## Run In A Prepared A100 Environment

Use one worker per GPU. The script sets `CUDA_VISIBLE_DEVICES` for each subprocess.

Example shape:

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

Template variables are shell-quoted by default:

- `{prompt}`
- `{image_path}`
- `{geneval_output_path}`
- `{seed}`
- `{sample_id}`
- `{candidate_id}`
- `{candidate_index}`
- `{gpu}`
- `{qwen_model_path}`

If your downstream script needs unquoted raw strings, use:

- `{prompt_raw}`
- `{image_path_raw}`
- `{geneval_output_path_raw}`
- `{qwen_model_path_raw}`

## Expected Geneval JSON

The normalizer accepts either structured constraints:

```json
{
  "score": 0.75,
  "passed_constraints": [
    {"type": "color_mismatch", "target": "apple", "expected": "red", "detected": "red"}
  ],
  "failed_constraints": [
    {"type": "count_mismatch", "target": "apple", "expected": 3, "detected": 2}
  ],
  "uncertain_constraints": []
}
```

or Geneval-style checks:

```json
{
  "score": 0.66,
  "expected": {
    "objects": ["apple", "plate"],
    "count": {"apple": 3},
    "color": {"apple": "red", "plate": "blue"}
  },
  "detected": [
    {"label": "apple", "color": "red"},
    {"label": "apple", "color": "red"},
    {"label": "plate", "color": "blue"}
  ],
  "checks": {
    "object_presence": true,
    "counting": false,
    "color_binding": true
  },
  "failure_reason": "expected 3 apples, detected 2"
}
```

The saved diagnostic includes:

- score;
- passed constraints;
- failed constraints;
- uncertain constraints;
- checks;
- failure_reason;
- critical_failure_types;
- image path;
- candidate index;
- seed and GPU metadata.

## Recommended Scale-Up

1. Run `--plan-only` for 10 prompts.
2. Run real generation + Geneval for 10 prompts x 4 candidates.
3. Inspect `candidate_diagnostics.jsonl`.
4. Use `teacher_diagnostics.jsonl` to call GPT teacher.
5. Only after the 10-prompt pilot is clean, expand to 50 prompts.
