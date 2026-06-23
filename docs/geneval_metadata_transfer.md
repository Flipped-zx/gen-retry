# Geneval Metadata Transfer

本文说明 official Geneval evaluation result 如何转换为 Gen-Retry 的 teacher diagnostic，并解释为什么不能直接把 Geneval 原始 `reason` 当作 SFT 输入。

## 1. 总体结论

这个转换过程是合理的，但前提是：

```text
不要直接把 official Geneval 原始输出交给 teacher。
```

Official Geneval 原始输出是 evaluator/debug 格式。它适合记录检测结果和评测原因，但不适合作为 retry policy 的直接训练状态。

我们当前 pipeline 会先把 official Geneval 输出转换为结构化 diagnostic：

```text
official Geneval result
-> official_geneval_adapter
-> teacher_diagnostics.selected.jsonl
-> build_teacher_retry_actions.py
-> teacher_retry_action
-> build_sft_trajectories.py
```

相关代码：

```text
src/gen_retry/evaluators/official_geneval_adapter.py
src/gen_retry/teacher/build_retry_action.py
src/gen_retry/eval/diagnostic_normalizer.py
scripts/run_geneval_select_teacher_diagnostics.py
scripts/build_teacher_retry_actions.py
scripts/build_sft_trajectories.py
```

## 2. Official Geneval 原始输出

Official Geneval `evaluation/evaluate_images.py` 对每张图输出一行 JSON。典型格式：

```json
{
  "filename": "data/runs/qwen_geneval_official/images_geneval/00080/samples/00002.png",
  "tag": "counting",
  "prompt": "a photo of three apples",
  "correct": false,
  "reason": "expected apple>=3, found 2",
  "metadata": "{\"tag\": \"counting\", \"include\": [{\"class\": \"apple\", \"count\": 3}], \"exclude\": [{\"class\": \"apple\", \"count\": 4}], \"prompt\": \"a photo of three apples\"}",
  "details": "{\"apple\": [[120, 90, 230, 210, 0.96], [260, 95, 370, 220, 0.93]]}"
}
```

字段含义：

| Field | Meaning |
|---|---|
| `filename` | 被评测图片路径。 |
| `tag` | Geneval 任务类型，如 `counting`, `colors`, `position`。 |
| `prompt` | 生图 prompt。 |
| `correct` | 该图片是否通过 Geneval。 |
| `reason` | 失败原因，通常是自然语言短句。 |
| `metadata` | 原始 prompt metadata，字符串化 JSON，包含 `include` / `exclude` / `position` 等约束。 |
| `details` | detector 检测结果，字符串化 JSON，包含检测到的类、bbox、score。 |

这个格式的问题是：它只告诉我们结果，不直接告诉 teacher 应该如何 preserve/repair。

## 3. Gen-Retry Teacher Diagnostic 格式

我们通过 `official_geneval_adapter.py` 把上面的 official result 转成：

```json
{
  "id": "00080_cand_02",
  "sample_id": "00080",
  "candidate_index": 2,
  "image_path": "data/runs/qwen_geneval_official/images_geneval/00080/samples/00002.png",
  "first_attempt_prompt": "a photo of three apples",
  "diagnostic": {
    "prompt": "a photo of three apples",
    "category": "counting",
    "expected": {
      "objects": ["apple"],
      "count": {"apple": 3},
      "exclude": [
        {"class": "apple", "count": 4}
      ]
    },
    "detected": [
      {
        "label": "apple",
        "bbox": [120, 90, 230, 210],
        "score": 0.96
      },
      {
        "label": "apple",
        "bbox": [260, 95, 370, 220],
        "score": 0.93
      }
    ],
    "checks": {
      "object_presence": true,
      "counting": false,
      "extra_object": true
    },
    "score": 0.0,
    "passed_constraints": [
      {
        "type": "object_presence",
        "target": "apple",
        "expected": "present",
        "detected": "present",
        "status": "passed",
        "details": {}
      }
    ],
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
  },
  "generator_metadata": {
    "generator": "qwen-image"
  }
}
```

这个格式才是 GPT teacher 的输入。

## 4. 字段映射

转换规则：

| Official Geneval field | Gen-Retry field | Notes |
|---|---|---|
| `filename` | `image_path` | 用于审计和后续 retry 执行，不作为训练目标。 |
| `prompt` | `first_attempt_prompt`, `diagnostic.prompt` | first-attempt generation prompt。 |
| `tag` | `diagnostic.category` | Geneval task category。 |
| `metadata.include` | `diagnostic.expected.objects/count/color/spatial` | 把约束从 Geneval metadata 转为统一 expected schema。 |
| `metadata.exclude` | `diagnostic.expected.exclude` | 通常用于 counting 上限或 extra object 检查。 |
| `details` | `diagnostic.detected` | detector outputs，保留用于诊断和审计。 |
| `correct` | `diagnostic.score`, `diagnostic.checks` | 单图 score 通常是 `1.0` or `0.0`。 |
| `reason` | `diagnostic.failure_reason`, `failed_constraints` | 自然语言失败原因会被结构化成失败约束。 |

## 5. Normalized Diagnostic

`build_teacher_retry_actions.py` 会进一步调用 `normalize_geneval_diagnostic()`，把 teacher diagnostic 转成更接近 policy state 的结构：

```json
{
  "prompt": "a photo of three apples",
  "category": "counting",
  "passed_constraints": [
    {
      "type": "object_presence",
      "target": "apple",
      "status": "passed"
    }
  ],
  "failed_constraints": [
    {
      "type": "counting",
      "target": "apple",
      "status": "failed",
      "expected": 3,
      "detected": 2
    }
  ],
  "failure_types": ["count_mismatch"],
  "preserve_candidates": [
    {
      "target": "apple",
      "property": "presence",
      "value": true
    }
  ],
  "repair_targets": [
    {
      "skill": "quantity_counting",
      "target": "apple",
      "failure_type": "count_mismatch",
      "instruction": "Render exactly 3 separate visible apple instances."
    }
  ],
  "failure_reason": "expected apple>=3, found 2"
}
```

这个 normalized diagnostic 的作用：

- 明确哪些约束已经通过；
- 明确哪些约束失败；
- 提取 failure type；
- 生成 preserve candidates；
- 生成 repair targets；
- 为 GPT teacher 提供更稳定的 action state。

## 6. Teacher Action 示例

GPT teacher 应该基于 `diagnostic` 和 `normalized_diagnostic` 输出严格 JSON：

```json
{
  "decision": "retry",
  "failure_types": ["count_mismatch"],
  "skills_to_call": ["quantity_counting"],
  "preserve_constraints": [
    "Keep the apples clearly visible."
  ],
  "repair_constraints": [
    "Render exactly three separate apples."
  ],
  "repair_strategy": "Preserve object presence and repair only the count.",
  "retry_prompt": "A photo of exactly three clearly separated apples.",
  "expected_improvement": [
    "The retry should satisfy the counting check."
  ],
  "regression_risks": [
    "The retry might change object visibility or add extra apples."
  ]
}
```

这就是后续 SFT trajectory 的核心 supervision target。

## 7. 为什么这个过程合理

### 7.1 Official Geneval 是 evaluator 输出，不是 policy state

Official Geneval 原始输出面向评测：

```text
image -> pass/fail -> reason
```

但 teacher 和 SFT 需要的是 retry policy state：

```text
expected constraints
detected state
passed constraints
failed constraints
preserve targets
repair targets
skill routing
```

所以中间必须有 adapter 和 normalizer。

### 7.2 Teacher 需要 preserve/repair 分离

Retry 训练最关键的是：

```text
修失败的，不要破坏已经正确的。
```

直接给 teacher `reason="expected apple>=3, found 2"`，teacher 可能只会写一个泛化 prompt。结构化 diagnostic 会让 teacher 明确：

```text
object_presence 已通过 -> preserve
counting 失败 -> repair
```

### 7.3 Detector 细节不应该成为训练目标

`bbox`, detector `score`, raw `details` 对诊断有用，但不应该出现在 assistant 训练 target 中。它们被保留在 diagnostic/raw report 里，用于审计和后续 pipeline，但最终 exporter 只使用 `assistant_trainable_messages`。

### 7.4 该格式可以自然支持真实二次 retry

现在第一阶段可以先训练：

```text
first diagnostic -> teacher retry action
```

后续加入真实二次 retry 时，只需要把 teacher action 的 `retry_prompt` 再送去生图，再跑 Geneval，并把第二次结果作为：

```json
{
  "retry_diagnostic": {}
}
```

或：

```json
{
  "retry_geneval_diagnostic": {}
}
```

接回 `build_sft_trajectories.py`。源格式不需要推翻。

## 8. 边界和风险

这个转换不是完美的，主要风险来自 official Geneval `reason` 的粒度。

需要特别抽样检查：

- `position`: 空间关系 reason 可能不够结构化；
- `color_attr`: 颜色绑定失败可能需要确认是哪一个对象颜色错；
- multi-word object: 如 `traffic light`, `baseball glove`，不能误判成颜色或属性；
- detector false negative: 真实图片里有对象但 detector 没检出；
- ambiguous image: 图像本身难以判断，不适合作为 teacher 数据。

推荐第一批筛选：

```text
0.25 <= prompt_score <= 0.75
candidate_policy = failed
```

并按 failure type 抽样人工检查若干条。

## 9. 运行命令

在生图完成后，先跑 official Geneval + 转换 + 筛选：

```bash
python3 scripts/run_geneval_select_teacher_diagnostics.py \
  --image-dir data/runs/qwen_geneval_official/images_geneval \
  --geneval-dir ../geneval \
  --object-detector-path /path/to/geneval/object_detector \
  --output-dir data/runs/qwen_geneval_official/selected \
  --min-prompt-score 0.25 \
  --max-prompt-score 0.75 \
  --candidate-policy failed
```

输出：

```text
data/runs/qwen_geneval_official/selected/teacher_diagnostics.selected.jsonl
```

然后调用 teacher：

```bash
python3 scripts/build_teacher_retry_actions.py \
  --input data/runs/qwen_geneval_official/selected/teacher_diagnostics.selected.jsonl \
  --output data/processed/teacher_retry_actions_geneval_official.jsonl \
  --failed-output data/failed/teacher_retry_actions_geneval_official_failed.jsonl
```

最后构建 SFT trajectory：

```bash
python3 scripts/build_sft_trajectories.py \
  --diagnostics data/runs/qwen_geneval_official/selected/teacher_diagnostics.selected.jsonl \
  --teacher-actions data/processed/teacher_retry_actions_geneval_official.jsonl \
  --output data/processed/geneval_retry_sft_official.jsonl
```

## 10. 判断标准

一条转换后的 teacher diagnostic 是合格的，当且仅当：

- `expected` 能还原原始 prompt 的对象、数量、颜色、空间约束；
- `checks` 能表达哪些子任务通过、哪些失败；
- `failed_constraints` 与 Geneval `reason` 一致；
- `preserve_candidates` 不为空且对应 passed checks；
- `repair_targets` 指向正确 skill；
- raw detector details 没有进入最终 assistant train target。

如果这些条件满足，从 Geneval 结果到 SFT 初始诊断问题的转换就是合理的。
