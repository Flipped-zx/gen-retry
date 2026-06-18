# Request 04: Run 50 Teacher Batch Manually

Run this from a normal terminal, not from Codex.

Reason: Codex could not reliably call the real teacher API from the sandboxed process because outbound Python network calls hit sandbox/network restrictions. The repository scripts are ready, but the real API batch should be launched by the user in a normal shell with the API environment variables set.

Do not print or commit API keys.

## 1. Set API Environment Variables

```bash
cd "/Users/z1x/code/Agentic Image/gen-retry"

export GEN_RETRY_TEACHER_BASE_URL="https://your-teacher-relay.example.com/v1"
export GEN_RETRY_TEACHER_API_KEY="replace_with_real_key"
export GEN_RETRY_TEACHER_MODEL="replace_with_model_name"
export GEN_RETRY_TEACHER_TIMEOUT="120"
export GEN_RETRY_TEACHER_MAX_RETRIES="3"
```

## 2. Prepare First 10 And Remaining 40

This assumes the 50-row diagnostics file exists at:

```text
data/smoke/geneval_diagnostics_50.jsonl
```

Create temporary slices:

```bash
mkdir -p data/tmp
head -n 10 data/smoke/geneval_diagnostics_50.jsonl > data/tmp/geneval_diagnostics_50_first10.jsonl
tail -n +11 data/smoke/geneval_diagnostics_50.jsonl > data/tmp/geneval_diagnostics_50_rows11_50.jsonl
```

Confirm counts:

```bash
wc -l \
  data/smoke/geneval_diagnostics_50.jsonl \
  data/tmp/geneval_diagnostics_50_first10.jsonl \
  data/tmp/geneval_diagnostics_50_rows11_50.jsonl
```

Expected counts: `50`, `10`, `40`.

## 3. Run First 10 Teacher Rows

```bash
python3 scripts/build_teacher_retry_actions.py \
  --input data/tmp/geneval_diagnostics_50_first10.jsonl \
  --output data/processed/teacher_retry_actions_50_first10.jsonl \
  --failed-output data/failed/teacher_retry_actions_50_first10_failed.jsonl
```

Check the split:

```bash
wc -l \
  data/processed/teacher_retry_actions_50_first10.jsonl \
  data/failed/teacher_retry_actions_50_first10_failed.jsonl
```

Proceed only if the first 10 look sane.

## 4. Resume To 50

```bash
python3 scripts/build_teacher_retry_actions.py \
  --input data/tmp/geneval_diagnostics_50_rows11_50.jsonl \
  --output data/processed/teacher_retry_actions_50_rows11_50.jsonl \
  --failed-output data/failed/teacher_retry_actions_50_rows11_50_failed.jsonl
```

Combine valid and failed outputs:

```bash
python3 - <<'PY'
from pathlib import Path

valid_parts = [
    Path("data/processed/teacher_retry_actions_50_first10.jsonl"),
    Path("data/processed/teacher_retry_actions_50_rows11_50.jsonl"),
]
failed_parts = [
    Path("data/failed/teacher_retry_actions_50_first10_failed.jsonl"),
    Path("data/failed/teacher_retry_actions_50_rows11_50_failed.jsonl"),
]

Path("data/processed/teacher_retry_actions_50.jsonl").write_text(
    "".join(path.read_text(encoding="utf-8") for path in valid_parts),
    encoding="utf-8",
)
Path("data/failed/teacher_retry_actions_50_failed.jsonl").write_text(
    "".join(path.read_text(encoding="utf-8") for path in failed_parts),
    encoding="utf-8",
)
PY
```

Confirm counts:

```bash
wc -l \
  data/processed/teacher_retry_actions_50.jsonl \
  data/failed/teacher_retry_actions_50_failed.jsonl
```

## 5. Build Full SFT Trajectories

```bash
python3 scripts/build_sft_trajectories.py \
  --diagnostics data/smoke/geneval_diagnostics_50.jsonl \
  --teacher-actions data/processed/teacher_retry_actions_50.jsonl \
  --output data/processed/geneval_retry_sft_50_full.jsonl \
  --trajectory-format full
```

## 6. Run Quality Checks

```bash
python3 scripts/check_sft_quality.py \
  --sft data/processed/geneval_retry_sft_50_full.jsonl \
  --diagnostics data/smoke/geneval_diagnostics_50.jsonl \
  --actions data/processed/teacher_retry_actions_50.jsonl

python3 scripts/safe_check.py
python3 -m compileall src scripts tests
```

## 7. Optional Export Checks

```bash
python3 scripts/export_sft.py \
  --input data/processed/geneval_retry_sft_50_full.jsonl \
  --format qwen \
  --output data/processed/export_qwen_50.jsonl

python3 scripts/export_sft.py \
  --input data/processed/geneval_retry_sft_50_full.jsonl \
  --format sharegpt \
  --output data/processed/export_sharegpt_50.jsonl

python3 scripts/export_sft.py \
  --input data/processed/geneval_retry_sft_50_full.jsonl \
  --format trl \
  --output data/processed/export_trl_50.jsonl

python3 scripts/check_export_quality.py \
  data/processed/export_qwen_50.jsonl \
  data/processed/export_sharegpt_50.jsonl \
  data/processed/export_trl_50.jsonl
```
