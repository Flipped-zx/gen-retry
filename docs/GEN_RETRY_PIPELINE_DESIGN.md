# Gen-Retry Pipeline 设计与当前分析

这份文档用于汇报当前 Gen-Retry 的 pipeline、initial plan API、teacher retry API 设计，以及我们从 10 条代表性轨迹和多轮实验中得到的结论。

核心观点：

> 我们不是只在学“如何写一个更强 prompt”。我们要训练的是一个 diagnostic-conditioned retry controller：它要学会什么时候 stop，什么时候 retry，基于 `latest` 还是 `best_so_far`，修哪些 failed atoms，保留哪些 passed atoms，以及如何避免 regression。

## 1. 任务定义

目标学生模型是 Qwen3-VL-4B-Instruct。我们希望它学到的链路是：

```text
GenEval2 diagnostic feedback
-> 识别 failed constraints
-> 选择 / 调用合适 skill
-> 保留 already-correct constraints
-> 修复 failed atoms
-> 决策 stop vs retry
-> 决策 latest vs best_so_far
-> 重新生成图像
-> 重新评估
-> submit 或继续 retry
```

这不是普通 prompt rewriting。普通 prompt rewriting 只优化下一条 prompt；我们的轨迹要教模型利用评测历史、atom 级反馈和 retry 记忆做连续决策。

## 2. 双机器闭环

当前系统拆成 API 机和 GPU 机。

| 机器 | 职责 | 大文件处理 |
|---|---|---|
| API 机 | initial plan API；teacher retry API；轨迹状态维护；导出 GPU metadata | 不生图 |
| GPU 机 | Qwen 生图；GenEval2 诊断；打包轻量结果回传 API 机 | 图片只留在 GPU 机 |

Git 只同步轻量 JSON：

- `data/exchange/api_to_gpu/.../generation_metadata.jsonl`
- `data/exchange/gpu_to_api/.../generation_manifest.jsonl`
- `data/exchange/gpu_to_api/.../normalized_reports.jsonl`
- 可选 `atom_rows.jsonl`，用于更细分析

图片不进入 Git。这样可以让 API 调用、GPU 生图和 GenEval2 诊断形成闭环，同时避免同步大量 image data。

## 3. Initial Plan API 设计

Initial plan 发生在第一次 Qwen 生图之前。

输入：

- 原始 GenEval2 prompt
- metadata 中的 VQA atoms / skills
- 可用 skill 列表

输出：

- `action_type = initial_plan`
- `parsed_constraints`
- `selected_skills`
- `generation_strategy`
- `initial_prompt`
- `generation_guards`

作用：

- 把原始 prompt 解析成 objects、counts、colors、attributes、relations、spatial constraints。
- 把自然语言 prompt 转成更适合生图和评测的 generation prompt。
- 在第一次生成前加入规划结构：分组、布局、可数性、可见性、anti-occlusion、negative constraints。

例子：

```text
Original prompt:
four striped trumpets, and six blue donuts to the left of three yellow bagels

Initial plan:
- exactly four striped trumpets
- exactly six blue donuts
- exactly three yellow bagels
- donuts grouped left of bagels
- all objects separated, countable, non-overlapping
```

Initial plan 的价值是：后续 retry 不再只面对 raw prompt，而是有一个结构化的初始规划和 guard 作为历史上下文。

## 4. Teacher Retry API 设计

Teacher retry API 在 GenEval2 诊断之后调用。若样本已经 pass，或被 regression guard 停止，则不再调用 teacher。

输入上下文：

- original prompt
- previous initial plan
- current generation prompt
- current GenEval2 normalized report
- failed atoms / passed atoms
- score、failed count、critical failure types
- retry history
- memory diff：fixed、persistent、new、regressed constraints
- best previous attempt 和 latest attempt
- retry budget
- available skills

输出：

- `action_type = retry_replan`
- `decision`
- `branch_source`: `latest` 或 `best_so_far`
- `branch_source_round`
- `diagnosis`
- `repair_constraints`
- `preserve_constraints`
- `regression_risks`
- `skill_revision`
- `regeneration_strategy`
- `retry_prompt`
- `expected_improvement`

关键点：teacher retry 不是只看当前 prompt，而是看完整轨迹状态。它需要判断当前失败来自哪里、哪些东西已经对了、上次 retry 是否引入了新失败、是否应该回到 best_so_far。

## 5. Stop / Retry / Branch 策略

Controller 主要学三类决策。

Stop：

- GenEval2 所有 atoms 通过时 stop。
- 出现 large regression 时 stop 或排除出正常续跑。
- retry budget 用尽时 stop。

Retry：

- 修 persistent failed atoms。
- 修上一次 retry 新引入的 failures。
- 如果分数提升但仍有关键 atoms 失败，可以继续 retry。

Branch：

- 如果 latest 提升且没有严重 regression，基于 `latest` 继续。
- 如果 latest 损坏了之前正确的 atoms，基于 `best_so_far` 继续。
- preserve constraints 应来自所选择的 branch，而不是盲目相信 latest。

这就是我们和普通 prompt rewriting 的核心区别：训练目标是 stateful retry behavior。

## 6. 10 条代表性轨迹说明了什么

轨迹 review 文件：

- `data/analysis/geneval2_retry_10_case_review.md`

这 10 条轨迹覆盖了不同 retry 行为。

| Case | 行为 | 学习信号 |
|---|---|---|
| A | 初始生成已经 pass | 需要学会直接 stop，不做无意义 retry |
| B | 第一次 teacher retry 后 pass | failed atoms 可以被修复，同时 preserve passed atoms |
| C | 第二次 teacher retry 后 pass | latest regression 后可以从 `best_so_far` 恢复 |
| D | 第一次 retry 明显提升但未 pass | 分数提升但仍有 failed atoms 时应继续 |
| E | round1 regression，round2 recovery | memory 和 branch 选择很重要 |
| F | 两轮小幅稳定提升 | 需要考虑 diminishing returns 和 retry budget |
| G | 修了一些约束但引入新失败 | prompt-only retry 会 trade off，需要 regression control |
| H | 小幅 regression 但未停止 | 不是所有负 delta 都应视为 catastrophic |
| I | 第一次 retry large regression | 需要 regression guard |
| J | 第二次 retry large regression | 后续 retry 仍可能失败，stop policy 防止坏轨迹继续污染 |

这些 case 支持我们的训练目标：让模型学习 atom-level repair、preservation、branch selection 和 stop decision。

## 7. 当前量化结果

数据范围：

- 100 个 GenEval2 prompts。
- 每个 prompt 初始生成 5 个 Qwen candidates。
- 初始生成共 500 张图。
- Round0 initial pass：29 / 500。

多轮结果：

| Stage | Evaluated samples | Avg delta | Improved | Worse | Passed | Large regression / stopped |
|---|---:|---:|---:|---:|---:|---:|
| Round1 vs Round0 | 471 | +0.0193 | 279 | 192 | 37 | 38 |
| Round2 vs Round1 | 396 | +0.0077 | 220 | 176 | 23 | 28 |
| Round3 vs Round2 | 345 | -0.0051 | 176 | 169 | 15 | 29 |

结论：

- Round1 和 Round2 平均分是正向提升，说明 teacher retry 有真实修复能力。
- Round3 开始基本走平甚至略降，说明后续 retry 需要更强的 regression control 和 branch/prompt policy。
- 这不是“方法没用”，而是说明 prompt-only retry 到后期会遇到 tradeoff。

100x5 sampling 是有价值的：

- 92 / 100 个 prompts 在 5 个 candidates 中出现多种 failed-constraint signatures。
- 71 / 100 个 prompts 出现多种 failure-type signatures。
- 68 / 100 个 prompts 出现多种 skill signatures。

所以 5 次采样不是简单重复，而是在暴露同一 prompt 下的不同失败模式。

## 8. Round4 Canonical Display Ablation

我们做了一个 selective round4 小实验，给 teacher 加了布局偏好：

```text
GEN_RETRY_REPLAN_STYLE=canonical_display
```

这个偏好鼓励 teacher 使用 plain background、rows、grids、bands、zones、visible / countable / non-overlapping objects。

Round4 selective 范围：

- 64 条样本。
- 40 条 high-potential `best_so_far_promising`。
- 12 条 latest-control。
- 12 条 count-hard-control。
- API/package failures：0。
- teacher output quality critical issues：0。

GPU 生图 + GenEval2 后：

| Metric | Value |
|---|---:|
| Samples | 64 |
| Avg previous score | 0.8944 |
| Avg round4 score | 0.8121 |
| Avg delta | -0.0822 |
| Median delta | -0.0785 |
| Improved | 11 |
| Worse | 53 |
| Passed | 3 |
| Large regressions at -0.2 delta | 8 |

解释：

- Canonical display 是一个合理假设，但当前结果说明它不能全局套用。
- 它可能让布局更可数，但也可能过度重写场景，损坏 relation、attribute binding 或 object identity。
- 因此 canonical display 更应该作为 conditional skill，而不是默认全局 retry style。
- 这个结果反而强化了 controller 的必要性：模型必须学会什么时候应该大幅重排布局，什么时候应该只做局部修复。

## 9. 当前设计结论

1. Initial plan 能提供结构化初始 prompt，但不能消除所有 count / relation / attribute failures。
2. Teacher retry 有修复能力，round1 和 round2 的平均提升证明了这一点。
3. Prompt-only retry 不稳定，可能修掉一部分 atoms，同时引入新失败。
4. `best_so_far` branch 是必要的，尤其在 latest regression 后。
5. Passed atoms 必须显式 preserve，否则 retry 会破坏已经正确的约束。
6. 后续 rounds 应该 selective，不应该无脑全量继续。
7. Canonical row/grid layout 应由 failure type 和上下文触发，不能全局使用。

## 10. 最终学生模型应该学什么

最终 SFT / controller 训练目标应包含：

- 读取 GenEval2 atoms，并分类 failed constraints。
- 区分 failed atoms 和 passed atoms。
- 选择 skills：count、object、attribute、color、spatial、relation、visibility、anti-occlusion、negative constraints。
- 决策 `stop` vs `retry`。
- 决策 `latest` vs `best_so_far`。
- 只针对 failed / regressed atoms 写 repair constraints。
- 从所选 branch 中 preserve passed constraints。
- 在 retry 前预测 regression risks。
- 避免把局部失败改造成全局重写，从而引入新错误。

一句话总结：

> 我们的训练目标不是 prompt engineer，而是一个会读诊断、会记忆、会选择分支、会控制回归风险的 retry agent。

