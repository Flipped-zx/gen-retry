# Gen-Retry SFT Strategy

## What The Student Should Learn

Target model: Qwen3-VL-4B-Instruct.

Gen-Retry SFT should teach the student to act like a diagnostic-conditioned retry agent, not like a generic prompt rewriter. Given a source prompt and Geneval diagnostic feedback from a failed generation, the student should learn to:

1. parse the intended object, count, color, spatial, presence, and visibility constraints;
2. identify failed constraints from structured diagnostic feedback;
3. preserve constraints that already passed;
4. route failures to the correct retry skill;
5. produce a targeted repair prompt or retry action;
6. retry generation through the expected tool-call pattern;
7. re-check the retry result;
8. submit only when the retry improves the failed constraints without regressing passed constraints.

## SFT Data Shapes

### Compact Retry Planner SFT

Compact planner rows teach a direct mapping:

```text
diagnostic + normalized failures -> teacher retry action
```

This is useful for early bootstrapping because it isolates the planner behavior: failure typing, skill selection, preserve/repair separation, targeted retry prompt, expected improvement, and regression risks.

### Full Retry Episode SFT

Full episode rows teach the whole agent loop:

```text
parse constraints
-> generate first attempt
-> judge first attempt
-> receive Geneval diagnostic
-> query retry skill
-> repair prompt / retry action
-> generate retry
-> judge retry
-> submit or discard
```

The current smoke data uses mocked generation and mocked retry judging. This is acceptable for SFT structure as long as training targets are assistant-only and raw detector/tool/mock outputs are masked.

### Transition-Level SFT

Transition-level SFT would split full episodes into smaller state-action examples:

```text
state_t -> assistant_action_t
```

This can improve coverage for individual behaviors such as skill routing or submit/discard decisions. It should be added after the full episode exporter is stable, because transition splitting must preserve the same masking rules.

## Coding-Agent Analogy

Gen-Retry is structurally similar to coding-agent SFT:

```text
failed attempt
-> structured error feedback
-> targeted repair
-> verification
-> submit if fixed
```

For a coding agent, the error feedback might be a compiler error or test failure. For Gen-Retry, the feedback is a Geneval diagnostic. The training target is not the failed output or raw logs; it is the assistant behavior that interprets feedback, repairs the right part, avoids regressions, and verifies the retry.

## Trainable Versus Masked Data

Train:

- assistant diagnostic summaries;
- assistant tool calls;
- assistant skill routing;
- assistant retry decisions;
- assistant repair prompts;
- assistant submit/discard decisions.

Mask or exclude:

- raw Geneval detector outputs;
- bounding boxes and detector scores;
- tool observations;
- generated image metadata;
- mock judge outputs;
- user messages;
- API keys or environment values.

The source full SFT rows enforce this by separating `assistant_trainable_messages`, `tool_observations`, `raw_detector_outputs`, and `non_trainable_context`. Exported rows should use only `assistant_trainable_messages`.

## Scaling Plan

### 5 Smoke

Purpose: validate schemas, masking, exporter compatibility, and quality checks. The current 5-row smoke set is the local baseline.

Required before moving on:

- SFT quality check passes;
- Qwen, ShareGPT, and TRL exports pass export quality checks;
- no raw detector metadata appears in assistant train targets.

### 50 Quality Check

Purpose: verify failure-type coverage and teacher API reliability on a small but meaningful batch.

The 50 set should cover:

- counting;
- color binding;
- spatial relation;
- object presence;
- mixed failures;
- visibility and occlusion.

Run this from a normal terminal if the Codex sandbox cannot reliably access the teacher API.

### 500 Pilot

Purpose: train or dry-run a small pilot dataset and inspect model behavior.

Use 500 only after the 50-batch review shows:

- valid teacher action rate is high;
- skill routing is aligned;
- preserve/repair fields are consistently separated;
- retry prompts are targeted;
- regression risks are present.

### 5k+ SFT

Purpose: build a real SFT corpus after schema, teacher, filtering, and exporter quality are stable.

At this scale, add deduplication, per-category balancing, teacher-action audits, and automated holdout checks.

## Filtering Before Training

Reject or quarantine rows with:

- failure type and skill mismatch;
- missing preserve/repair separation;
- generic retry prompts that do not target the failed constraint;
- missing regression awareness;
- raw detector outputs in assistant targets;
- tool observations in assistant targets;
- API-key-like strings anywhere in exported rows;
- malformed JSONL;
- missing submit/discard decision;
- contradictory or empty teacher retry actions.

Rows with warnings should be manually reviewed before entering a pilot training split.

## Recommended Order Before RL

1. Finish and harden the SFT data builder.
2. Export Qwen-compatible, ShareGPT/LLaMA-Factory, and TRL conversational files.
3. Train a small LoRA on 500 or 1k filtered examples.
4. Evaluate retry behavior on held-out diagnostics.
5. Only then design and run RL.

RL should not start until SFT reliably teaches the core retry loop and masking/export quality is stable.
