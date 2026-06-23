# Gen-Retry SFT Data Format

本文定义 Gen-Retry 第一阶段 SFT 数据格式。核心目标不是训练一个普通 prompt rewriter，而是训练一个能读 Geneval 诊断、保留已满足约束、只修失败约束、调用合适技能、重试并验证的 image retry agent。

## 1. 数据链路

当前数据链路分四层：

```text
Qwen-Image first generation
-> official Geneval evaluation
-> selected teacher diagnostics
-> GPT teacher retry actions
-> SFT trajectory rows
-> downstream export formats
```

对应文件：

```text
data/runs/qwen_geneval_official/images_geneval/
  00000/metadata.jsonl
  00000/samples/00000.png
  ...

data/runs/qwen_geneval_official/selected/
  geneval_results.jsonl
  candidate_diagnostics.jsonl
  prompt_selection.jsonl
  selected_candidate_diagnostics.jsonl
  teacher_diagnostics.selected.jsonl

data/processed/
  teacher_retry_actions_geneval_official.jsonl
  geneval_retry_sft_official.jsonl
  export_qwen_*.jsonl
  export_sharegpt_*.jsonl
  export_trl_*.jsonl
```

`geneval_results.jsonl` 是官方 Geneval 原始输出，不直接训练。训练入口从 `teacher_diagnostics.selected.jsonl` 开始。

## 2. Teacher Diagnostic Row

文件：

```text
teacher_diagnostics.selected.jsonl
```

每行是一个失败 first-attempt candidate。这个格式是 GPT teacher 的输入，也是后续 SFT builder 查找原始诊断的输入。

必需字段：

```json
{
  "id": "00042_cand_01",
  "sample_id": "00042",
  "candidate_index": 1,
  "image_path": "data/runs/.../00042/samples/00001.png",
  "first_attempt_prompt": "a photo of three apples",
  "diagnostic": {},
  "generator_metadata": {},
  "selection_metadata": {},
  "geneval_report": {}
}
```

字段定义：

| Field | Type | Train? | Meaning |
|---|---:|---:|---|
| `id` | string | context | Candidate id, usually `{sample_id}_cand_{index}`. |
| `sample_id` | string | context | Geneval prompt id / directory id. |
| `candidate_index` | int | context | The image index under one prompt. |
| `image_path` | string | no | First-attempt image path for audit and possible retry execution. |
| `first_attempt_prompt` | string | context | Prompt used to generate the first attempt. |
| `diagnostic` | object | context | Normalized Geneval diagnostic consumed by teacher and SFT builder. |
| `generator_metadata` | object | no | Generator name, model path, seed, GPU, etc. |
| `selection_metadata` | object | no | Prompt-level filtering score and policy. |
| `geneval_report` | object | no | Normalized report with raw official output retained for audit. |

`diagnostic` is the important part:

```json
{
  "prompt": "a photo of three apples",
  "category": "counting",
  "expected": {
    "objects": ["apple"],
    "count": {"apple": 3}
  },
  "detected": [
    {"label": "apple", "bbox": [0, 0, 10, 10], "score": 0.95}
  ],
  "checks": {
    "object_presence": true,
    "counting": false
  },
  "score": 0.0,
  "passed_constraints": [],
  "failed_constraints": [
    {
      "type": "count_mismatch",
      "target": "apple",
      "expected": 3,
      "detected": 2,
      "status": "failed",
      "details": {}
    }
  ],
  "uncertain_constraints": [],
  "failure_reason": "expected apple>=3, found 2",
  "critical_failure_types": ["count_mismatch"]
}
```

Important: `detected`, `bbox`, `score`, and raw detector details are context/audit fields. They must not become train targets.

## 3. Prompt Selection Row

文件：

```text
prompt_selection.jsonl
```

每行对应一个 Geneval prompt group。因为每个 prompt 生成 `n_samples=4` 张图，所以 prompt-level score 是 4 张里通过 Geneval 的比例：

```text
0.0, 0.25, 0.5, 0.75, 1.0
```

格式：

```json
{
  "sample_id": "00042",
  "prompt": "a photo of three apples",
  "category": "counting",
  "prompt_score": 0.5,
  "correct_count": 2,
  "total_count": 4,
  "selected": true,
  "candidate_ids": [
    "00042_cand_00",
    "00042_cand_01",
    "00042_cand_02",
    "00042_cand_03"
  ]
}
```

推荐第一批 retry 数据筛选：

```text
0.25 <= prompt_score <= 0.75
candidate_policy = failed
```

理由：完全失败的 prompt 可能太难或检测不可靠，全部成功的 prompt 不需要 retry；中间分数更容易形成“同一约束空间下，有失败可修”的样本。

## 4. Teacher Retry Action Row

文件：

```text
teacher_retry_actions_geneval_official.jsonl
```

每行是 GPT teacher 对一个 diagnostic 给出的下一步 action：

```json
{
  "id": "00042_cand_01",
  "teacher_mode": "api",
  "diagnostic": {},
  "normalized_diagnostic": {},
  "teacher_retry_action": {
    "decision": "retry",
    "failure_types": ["count_mismatch"],
    "skills_to_call": ["quantity_counting"],
    "preserve_constraints": [
      "Keep the apple objects clearly visible."
    ],
    "repair_constraints": [
      "Render exactly three apples."
    ],
    "repair_strategy": "Preserve object presence and repair only the count.",
    "retry_prompt": "A photo of exactly three clearly separated apples.",
    "expected_improvement": [
      "The retry should satisfy the counting check."
    ],
    "regression_risks": [
      "The retry might change already-visible objects."
    ]
  }
}
```

`teacher_retry_action` 的严格 schema：

| Field | Type | Meaning |
|---|---:|---|
| `decision` | enum | `retry`, `submit`, or `discard`. |
| `failure_types` | string[] | Normalized failure labels, e.g. `count_mismatch`. |
| `skills_to_call` | string[] | Skill names from our retry skill library. |
| `preserve_constraints` | string[] | Constraints that already passed and should not regress. |
| `repair_constraints` | string[] | Failed constraints that the retry must fix. |
| `repair_strategy` | string | Natural-language plan tying preserve and repair together. |
| `retry_prompt` | string | Prompt/action text used for retry generation. |
| `expected_improvement` | string[] | What should improve after retry. |
| `regression_risks` | string[] | What could regress and needs attention. |

This schema is intentionally stricter than free-form chain-of-thought. It gives SFT stable action targets and makes quality checks possible.

## 5. Source SFT Trajectory Row

文件：

```text
geneval_retry_sft_official.jsonl
```

Each row is one SFT source trajectory. Default format is `full_episode`.

Top-level shape:

```json
{
  "id": "00042_cand_01",
  "trajectory_format": "full_episode",
  "masking_metadata": {},
  "assistant_trainable_messages": [],
  "tool_observations": [],
  "raw_detector_outputs": {},
  "non_trainable_context": {},
  "messages": [],
  "episode_steps": [],
  "images": [],
  "diagnostic": {},
  "normalized_diagnostic": {},
  "teacher_retry_action": {},
  "mock_retry_diagnostic": {},
  "outcome": {}
}
```

Field policy:

| Field | Train? | Meaning |
|---|---:|---|
| `id` | context | Stable row id. |
| `trajectory_format` | context | `full_episode` or `compact`. |
| `masking_metadata` | no | Explicit train/exclude policy. |
| `assistant_trainable_messages` | yes | Sole source of SFT training text. |
| `tool_observations` | no | Tool outputs, judge outputs, skill observations. |
| `raw_detector_outputs` | no | Raw or high-detail Geneval detector payloads. |
| `non_trainable_context` | no | Source prompt, expected constraints, generated image metadata. |
| `messages` | mixed/source only | Full conversation trace for audit/debug; do not export directly. |
| `episode_steps` | no | Structured trace for audit and analysis. |
| `images` | no | Optional image refs; not current train target. |
| `diagnostic` | context/no | Compact first-attempt diagnostic. |
| `normalized_diagnostic` | context/no | Preserve/repair/failure-type normalization. |
| `teacher_retry_action` | context/no | Teacher action object used to construct targets. |
| `mock_retry_diagnostic` | no | Mock retry judge result unless replaced by real retry evaluation. |
| `outcome` | no | Submit/discard status and notes. |

## 6. Assistant Trainable Messages

Only `assistant_trainable_messages` should be exported for training.

Each item:

```json
{
  "role": "assistant",
  "content": "<tool_call>{...}</tool_call>",
  "train": true,
  "target_type": "tool_call"
}
```

Target types:

| `target_type` | Meaning |
|---|---|
| `diagnostic_summary` | Parse prompt constraints or receive normalized Geneval diagnostic. |
| `tool_call` | Call `generate_image`, `judge_image`, or `query_skill`. |
| `repair_prompt_and_retry_decision` | Produce preserve/repair constraints, retry action, and retry prompt. |
| `submit_or_discard_decision` | Submit, discard, or stop based on retry judge result. |
| `assistant_action` | Fallback category for assistant messages outside the above tags. |

The assistant messages use tagged JSON blocks:

```text
<parse_constraints>{...}</parse_constraints>
<tool_call>{"name": "query_skill", "arguments": {...}}</tool_call>
<receive_geneval_diagnostic>{...}</receive_geneval_diagnostic>
<repair_prompt>{...}</repair_prompt>
<submit>{...}</submit>
```

The tags are deliberate. They make downstream checks and transition-level splitting easy while preserving a chat-compatible target.

## 7. Compact Format

Compact rows are supported for early bootstrapping:

```text
diagnostic + normalized_diagnostic -> teacher_retry_action
```

They contain `messages`, `diagnostic`, `normalized_diagnostic`, and `teacher_retry_action`, but do not teach the full loop. Use compact rows only when testing the planner behavior in isolation.

Default training should use `full_episode`, because our target model should learn the agent loop, not only one-step prompt rewriting.

## 8. Export Formats

Source SFT rows are not final training files. They are exported into downstream formats:

```bash
python3 scripts/export_sft.py \
  --input data/processed/geneval_retry_sft_official.jsonl \
  --format qwen \
  --output data/processed/export_qwen_official.jsonl
```

Supported formats:

| Format | Output shape | Train source |
|---|---|---|
| `qwen` | `{messages, loss_mask}` | Assistant-only messages. |
| `sharegpt` | LLaMA-Factory style `{conversations}` | One sanitized human prompt plus one GPT target. |
| `trl` | TRL conversational `{messages}` | Assistant-only messages. |

All exporters use only `assistant_trainable_messages`. They must never copy raw detector outputs, tool observations, image metadata, or mock judge outputs into train targets.

## 9. Why This Format

### 9.1 We are training a retry agent, not a prompt rewriter

The model must learn:

```text
diagnose -> preserve -> repair -> call skill -> retry -> verify -> submit/discard
```

A flat pair like:

```text
bad prompt -> better prompt
```

would erase the key behavior: preserving already-correct constraints and repairing only failed constraints.

### 9.2 Geneval feedback is structured error feedback

Geneval plays the role that unit tests or compiler errors play for a coding agent. We keep:

- `checks` for pass/fail status;
- `failed_constraints` for repair targets;
- `passed_constraints` and `preserve_constraints` for anti-regression;
- `failure_reason` for natural-language diagnosis;
- raw detector outputs only for audit.

The training target is the assistant behavior that interprets feedback, not the detector output itself.

### 9.3 Masking is part of the data definition

Raw detector boxes, detector scores, mock judge outputs, and generated image paths are useful for building data, but they should not be learned as answer text. Separating `assistant_trainable_messages` from `tool_observations` and `raw_detector_outputs` prevents leakage.

This is why the source row is richer than the export row. The source row supports audit and future real retry execution; the export row contains only supervised targets.

### 9.4 Gen-Searcher reference

Gen-Searcher separates:

```text
agentic inference / tool use / search reasoning
-> final image generation from results
-> benchmark evaluation
```

The lesson for Gen-Retry is to keep trajectory data and image rendering/evaluation artifacts separated. We follow that by keeping first images, Geneval outputs, teacher actions, and trainable assistant targets as distinct layers.

### 9.5 GenEvolve reference

GenEvolve treats image generation as a tool-orchestrated visual trajectory and emits a program-like result that can be rendered by different generators. The lesson for Gen-Retry is that the agent policy should produce structured actions, not only prose.

Our equivalent structured action is:

```json
{
  "decision": "retry",
  "skills_to_call": ["quantity_counting"],
  "preserve_constraints": ["..."],
  "repair_constraints": ["..."],
  "retry_prompt": "..."
}
```

This lets us swap the renderer/evaluator later while preserving the same retry policy data.

### 9.6 The format can evolve to real retry episodes

Current full episodes can use mock retry judging. Once we add real second-attempt generation and second Geneval evaluation, the same schema can accept:

```json
{
  "retry_diagnostic": {
    "checks": {
      "object_presence": true,
      "counting": true
    },
    "failure_reason": ""
  }
}
```

The SFT builder already looks for fields such as `retry_diagnostic`, `second_diagnostic`, `improved_diagnostic`, or `retry_geneval_diagnostic` in teacher action rows. This means the source format does not need to be replaced when we move from mock retry to real retry; we only enrich the retry judge input.

## 10. Quality Requirements

A row should not enter SFT training if:

- `teacher_retry_action` is invalid or missing required keys;
- `decision=retry` but `skills_to_call`, `repair_constraints`, or `retry_prompt` is empty;
- preserve constraints are missing despite passed checks;
- repair constraints do not match failed constraints;
- skill choice does not match `failure_types`;
- retry prompt is generic and does not target the failed constraint;
- assistant train targets include `bbox`, detector `score`, raw detector fields, tool responses, image paths, or API-key-like strings;
- prompt-level selection metadata suggests the case is too easy or too broken for the intended split;
- official Geneval failure reason is ambiguous or contradicted by normalized constraints.

Run these checks before export:

```bash
python3 scripts/check_sft_quality.py data/processed/geneval_retry_sft_official.jsonl

python3 scripts/export_sft.py \
  --input data/processed/geneval_retry_sft_official.jsonl \
  --format qwen \
  --output data/processed/export_qwen_official.jsonl

python3 scripts/check_export_quality.py data/processed/export_qwen_official.jsonl
```

## 11. Recommended First-Batch Procedure

1. Generate 4 Qwen-Image candidates per Geneval prompt.
2. Run official Geneval.
3. Select prompt groups with `0.25 <= prompt_score <= 0.75`.
4. Keep failed candidates from selected prompt groups.
5. Build GPT teacher actions.
6. Build full SFT trajectory rows.
7. Run SFT and export quality checks.
8. Manually inspect a small sample by failure type before training.

This gives us a first SFT set that is small enough to audit, but already aligned with the final retry-agent behavior.
