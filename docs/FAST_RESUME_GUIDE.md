# Fast Resume Guide

Use this file first when resuming work. The goal is to start executing quickly, not to re-audit the whole repository.

## Current Completed State

- Stage completed: GenEval2 diagnosis + one-shot teacher `retry_replan` for the existing initial generations.
- Scope completed: 100 prompts x 5 candidates = 500 initial images.
- GenEval2 reports: 500.
- Raw trajectories: 500.
- `initial_success`: 29.
- `retry_ready`: 471.
- `error`: 0.
- Retry SFT rows: 471.

Key outputs:

- GenEval2 merged diagnostics: `data/geneval2_jobs/balanced100_all_candidates/normalized_reports.jsonl`
- Package manifest: `data/incoming_generation_results/geneval2_balanced_100x5_round0_with_eval/package_manifest.jsonl`
- Retry action manifest: `data/outgoing_retry_actions/geneval2_balanced_100x5_round0_gpt55/retry_action_manifest.jsonl`
- Raw trajectories: `data/raw_trajectories/geneval2_balanced_100x5_round0_gpt55/`
- SFT: `data/sft/geneval2_balanced_100x5_round0_retry_replan_sft.jsonl`
- Report: `docs/GENEVAL2_BALANCED100_RETRY_TRAJECTORY_REPORT.md`
- Summary: `data/analysis/geneval2_balanced100_retry_stage_summary.json`

## Fast Sanity Check

Run this before making claims, but do not spend a long turn re-auditing unless it fails:

```bash
python3 - <<'PY'
import json
from pathlib import Path
from collections import Counter

summary = json.loads(Path("data/analysis/geneval2_balanced100_retry_stage_summary.json").read_text())
print("summary counts:", summary["counts"])

traj = Path("data/raw_trajectories/geneval2_balanced_100x5_round0_gpt55")
statuses = Counter()
valid = 0
for path in traj.glob("*.json"):
    row = json.loads(path.read_text())
    statuses[row.get("status", "")] += 1
    action = row.get("retry_ready_action") or row.get("latest_teacher_action") or {}
    if isinstance(action, dict) and action.get("action_type") == "retry_replan":
        valid += 1
print("trajectory statuses:", dict(statuses))
print("valid retry_replan:", valid)
PY
```

Expected:

- `retry_ready`: 471
- `initial_success`: 29
- valid `retry_replan`: 471

## Teacher API

Use environment variables only. Do not write API keys into repo files.

```bash
export GEN_RETRY_TEACHER_BASE_URL="https://skyapi.duckdns.org/v1"
export GEN_RETRY_TEACHER_API_KEY="..."
export GEN_RETRY_TEACHER_MODEL="gpt-5.5"
export GEN_RETRY_TEACHER_TIMEOUT="180"
export GEN_RETRY_TEACHER_MAX_RETRIES="4"
```

Operational notes:

- `/models` showed `gpt-5.5` exists.
- `gpt-5.5` worked for the main pass, but later returned HTTP 503 for 32 tail samples.
- Those 32 were completed with the same relay using `gpt-5.4`; record this provenance if model purity matters.
- If `gpt-5.5` chat is 503, test `gpt-5.4` quickly instead of repeatedly re-preparing data.

## Parallel Strategy That Worked

For GenEval2:

- 4 shards worked on the A800 80GB.
- Memory was about 71.5GB / 80GB.
- Shard size was 125 candidates each.
- Use existing `scripts/run_geneval2_batch.py` with `--num-shards 4`, `--shard-index 0..3`, `--resume`.

For teacher API:

- API calls can run while GenEval2 is still running.
- Use completed GenEval2 checkpoints to snapshot partial inputs with:
  `scripts/snapshot_partial_geneval2_retry_inputs.py`
- Then run multiple `scripts/build_geneval2_retry_plans.py` workers.
- If relay starts returning 503, reduce API concurrency and increase `GEN_RETRY_TEACHER_MAX_RETRIES`.

## What Not To Repeat

- Do not rerun GenEval2 for the existing 500 images unless outputs are missing or corrupted.
- Do not redo teacher `retry_replan` for the 471 completed failed candidates unless intentionally regenerating teacher labels.
- Do not regenerate retry images as part of the completed stage; the current stage intentionally stopped at diagnosis + retry planning.
- Do not spend a long turn rediscovering paths; use the paths in this file first.

## Next Likely Work

If the user asks to continue the pipeline, the next practical stage is retry image generation:

1. Read the 471 `retry_ready` trajectories from `data/raw_trajectories/geneval2_balanced_100x5_round0_gpt55/`.
2. For each, use `retry_ready_action.retry_prompt`.
3. Generate retry images into a new output directory; do not overwrite initial images.
4. Re-evaluate retry images with GenEval2.
5. Compare score deltas, fixed constraints, regressions, and build accepted/rejected trajectory data.

If the user asks for SFT work, start from:

- `data/sft/geneval2_balanced_100x5_round0_retry_replan_sft.jsonl`
- `data/rejected/geneval2_balanced_100x5_round0_retry_replan_rejected.jsonl`

## Useful Repair Commands

Rebuild manifest from existing action packages:

```bash
python3 scripts/rebuild_retry_action_manifest.py \
  --output-dir data/outgoing_retry_actions/geneval2_balanced_100x5_round0_gpt55 \
  --expected-count 500
```

Re-export SFT:

```bash
python3 scripts/export_offline_retry_sft.py \
  --trajectories-dir data/raw_trajectories/geneval2_balanced_100x5_round0_gpt55 \
  --output data/sft/geneval2_balanced_100x5_round0_retry_replan_sft.jsonl \
  --rejected-output data/rejected/geneval2_balanced_100x5_round0_retry_replan_rejected.jsonl
```

Regenerate report:

```bash
python3 scripts/report_geneval2_retry_stage.py \
  --package-manifest data/incoming_generation_results/geneval2_balanced_100x5_round0_with_eval/package_manifest.jsonl \
  --diagnostic-jobs data/geneval2_jobs/balanced100_all_candidates/diagnostic_jobs.jsonl \
  --eval-results data/geneval2_jobs/balanced100_all_candidates/normalized_reports.jsonl \
  --retry-manifest data/outgoing_retry_actions/geneval2_balanced_100x5_round0_gpt55/retry_action_manifest.jsonl \
  --trajectory-dir data/raw_trajectories/geneval2_balanced_100x5_round0_gpt55 \
  --sft-output data/sft/geneval2_balanced_100x5_round0_retry_replan_sft.jsonl \
  --markdown-output docs/GENEVAL2_BALANCED100_RETRY_TRAJECTORY_REPORT.md \
  --summary-output data/analysis/geneval2_balanced100_retry_stage_summary.json \
  --all-candidates \
  --limit 500
```
