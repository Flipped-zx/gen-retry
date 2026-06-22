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
