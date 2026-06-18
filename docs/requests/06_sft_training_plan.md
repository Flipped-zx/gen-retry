# Request 06: SFT Training Plan

Goal: plan Qwen3-VL-4B-Instruct SFT after the 500-row pilot data passes quality checks.

Do not start training until the user explicitly requests it in a prepared training environment.

## Inputs

Preferred input after the 500 pilot:

```text
data/processed/export_qwen_500.jsonl
```

Optional compatibility inputs:

```text
data/processed/export_sharegpt_500.jsonl
data/processed/export_trl_500.jsonl
```

## Training Objective

Teach the model assistant-side Gen-Retry behavior:

- diagnostic summaries;
- tool calls;
- skill routing;
- retry decisions;
- repair prompts;
- submit/discard decisions.

Do not train on raw detector outputs, tool observations, generated image metadata, mock judge outputs, user messages, or secrets.

## Suggested Pilot

1. Train a small LoRA on 500 or 1k examples.
2. Keep a held-out diagnostic set for evaluation.
3. Evaluate whether the model:
   - identifies failed constraints;
   - preserves passed constraints;
   - routes to the right skill;
   - writes targeted retry prompts;
   - includes regression awareness;
   - avoids raw detector leakage in outputs.

## Before Scaling To 5k+

- Review category balance.
- Deduplicate prompts and diagnostics.
- Inspect teacher actions by failure type.
- Confirm export quality is clean.
- Confirm the SFT model improves retry behavior on held-out diagnostics.

## Deliverables For The Training Turn

- Training config proposal.
- Dataset split plan.
- Evaluation checklist.
- Rollback plan if the model learns generic prompt rewriting instead of diagnostic-conditioned repair.
