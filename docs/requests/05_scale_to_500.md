# Request 05: Scale Gen-Retry Data To 500

Goal: scale from the 50-row quality batch to a 500-row pilot without training, RL, image generation, or dependency installation.

## Preconditions

- `data/smoke/geneval_diagnostics_50.jsonl` exists.
- `data/processed/teacher_retry_actions_50.jsonl` has a high valid-action rate.
- `data/failed/teacher_retry_actions_50_failed.jsonl` is reviewed.
- `data/processed/geneval_retry_sft_50_full.jsonl` passes `scripts/check_sft_quality.py`.
- Qwen, ShareGPT, and TRL exports for the 50 set pass `scripts/check_export_quality.py`.

## Tasks

1. Create or locate 500 Geneval-style diagnostics with balanced coverage:
   - counting;
   - color binding;
   - spatial relation;
   - object presence;
   - mixed failures;
   - visibility and occlusion.
2. Store them at `data/smoke/geneval_diagnostics_500.jsonl` or a more appropriate `data/raw/` path.
3. Run the real teacher batch manually from a normal terminal in smaller chunks.
4. Build full SFT trajectories:

```bash
python3 scripts/build_sft_trajectories.py \
  --diagnostics data/smoke/geneval_diagnostics_500.jsonl \
  --teacher-actions data/processed/teacher_retry_actions_500.jsonl \
  --output data/processed/geneval_retry_sft_500_full.jsonl \
  --trajectory-format full
```

5. Run quality checks:

```bash
python3 scripts/check_sft_quality.py \
  --sft data/processed/geneval_retry_sft_500_full.jsonl \
  --diagnostics data/smoke/geneval_diagnostics_500.jsonl \
  --actions data/processed/teacher_retry_actions_500.jsonl

python3 scripts/safe_check.py
python3 -m compileall src scripts tests
```

6. Export and check downstream formats:

```bash
python3 scripts/export_sft.py \
  --input data/processed/geneval_retry_sft_500_full.jsonl \
  --format qwen \
  --output data/processed/export_qwen_500.jsonl

python3 scripts/export_sft.py \
  --input data/processed/geneval_retry_sft_500_full.jsonl \
  --format sharegpt \
  --output data/processed/export_sharegpt_500.jsonl

python3 scripts/export_sft.py \
  --input data/processed/geneval_retry_sft_500_full.jsonl \
  --format trl \
  --output data/processed/export_trl_500.jsonl

python3 scripts/check_export_quality.py \
  data/processed/export_qwen_500.jsonl \
  data/processed/export_sharegpt_500.jsonl \
  data/processed/export_trl_500.jsonl
```

## Review Criteria

- Valid teacher actions: target at least 95%.
- Failed teacher actions: inspect all failures.
- Critical SFT issues: must be 0.
- Export quality issues: must be 0 critical.
- Skill routing should match failure types.
- Preserve constraints and repair constraints must be separated.
- Retry prompts must target failed constraints without broad prompt drift.
- Regression risks must be present.
- Assistant train targets must not include raw detector outputs, tool observations, or API-key-like strings.
