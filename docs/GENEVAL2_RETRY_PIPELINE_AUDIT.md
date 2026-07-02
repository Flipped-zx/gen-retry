# GenEval2 Retry-Agent 数据管线审计报告

审计目标：核对当前 `gen-retry` 仓库是否已经支持面向 GenEval2 反馈驱动 retry agent 的 trajectory-level SFT，并与预期策略对齐。

审计方式：只读检查仓库代码、脚本、docs、`data/prompts/`、`data/raw_episodes*`、`data/sft/`、`data/processed/`、`data/rejected/`、`data/images/`。本报告未修改任何代码。

## 结论摘要

当前仓库已经实现了一个可运行的闭环雏形：

- GenEval2 prompt 子集准备、静态难度筛选、单图 GenEval2/Soft-TIFA-GM 评估入口。
- `gpt-5.5`/Seed 风格 teacher 的 `initial_plan` 和 `retry_replan` 结构化动作。
- `gpt-image-2` OpenAI-compatible 图像生成 adapter。
- GenEval2 atom-row 到结构化 `NormalizedEvalReport` 的归一化。
- raw episode 存储、stop rule、transition classification、compact SFT 和 tool-trajectory SFT 导出。

但当前数据还不能直接作为高质量 SFT pilot：

- 最大真实闭环集只有 20 个 prompt，不到预期 100-200。
- 每个 prompt 只生成 1 张初始图，没有 4-5 seeds/images。
- 主真实数据使用 `gpt-image-2`，不是后续 RL/学生环境中明确指定的目标生成器；是否与后续 RL generator 对齐仍是 unknown。
- `gpt-5.5` teacher + `gpt-image-2` generator 太强，初始通过率偏高，retry 状态太少。
- 真实失败类型高度集中在 `count_mismatch`，缺少足够的 object、attribute/color binding、spatial/position、多约束失败。
- retry 质量混合：主真实集 5 条初始失败 episode 中 3 条最终通过、2 条最终回归。
- stop rule 目前主要按 pass/budget 停止，没有显式 no-improvement 或 regression-too-large 早停。

## 1. 已实现内容

### Prompt sampling

相关文件：

- `scripts/prepare_geneval2_prompts.py`
- `scripts/select_geneval2_static_difficulty.py`
- `data/prompts/*.jsonl`

当前 prompt 来源分两类：

| 文件 | 行数 | 来源 | 说明 |
|---|---:|---|---|
| `data/prompts/geneval2_smoke_3.jsonl` | 3 | GenEval2 | smoke 集 |
| `data/prompts/geneval2_static_hard_30.jsonl` | 30 | GenEval2 | 静态 hard 筛选 |
| `data/prompts/geneval2_static_hard_next20.jsonl` | 20 | GenEval2 | 当前主真实闭环集使用 |
| `data/prompts/geneval2_static_medium_30.jsonl` | 30 | GenEval2 | 静态 medium 筛选 |
| `data/prompts/geneval2_static_position_20.jsonl` | 20 | GenEval2 | position/verb 高原子数子集 |
| `data/prompts/geneval2_static_retry_candidates_25.jsonl` | 25 | GenEval2 | retry 候选 |
| `data/prompts/geneval2_static_verb_20.jsonl` | 20 | GenEval2 | position/verb 高原子数子集 |
| `data/prompts/geneval_pilot_10.jsonl` | 10 | custom/manual | 早期 pilot prompt |
| `data/prompts/sample_prompts.jsonl` | 7 | custom/mock | mock collector prompt |

判断：

- GenEval2 prompt 抽取已实现，并保存 `prompt`、`source_index`、`atom_count`、`vqa_list`、`skills`。
- 已有若干静态筛选子集，但真实闭环生成的规模仍只有 smoke/小批量。
- 还没有达到预期 100-200 prompt pilot。

### Initial image generation

相关文件：

- `scripts/collect_real_episodes.py`
- `src/gen_retry/collectors/collect_episodes.py`
- `src/gen_retry/generators/real_generator_adapter.py`

实现方式：

- `EpisodeCollector` 先调用 teacher 的 `initial_plan`，再用 `initial_plan.initial_prompt` 调用 generator。
- `RealGeneratorAdapter` 当前实际支持 `gpt_image` backend，默认 model 为 `gpt-image-2`。
- OpenAI-compatible image API 通过环境变量配置：`GEN_RETRY_IMAGE_BASE_URL`、`GEN_RETRY_IMAGE_API_KEY`、`GEN_RETRY_IMAGE_MODEL` 等。
- 每次 API payload 固定 `n: 1`，因此每个 prompt 只有 1 张初始图。
- 图片保存为 `data/images/<episode_id>_attempt_<round>.png` 或对应子目录；sidecar 保存为 `.png.json`。

判断：

- 真实主数据集 `data/raw_episodes_real_hard_atom090_next20` 使用 `generator_name: gpt_image2`。
- 目前没有 seeds 字段，也没有每 prompt 4-5 初始候选图。
- `gemini_image`/`nano` backend 在当前 adapter 中仍是 `NotImplementedError`。

### Evaluation

相关文件：

- `scripts/run_geneval2_single_image.py`
- `src/gen_retry/evaluators/geneval2_adapter.py`
- `src/gen_retry/evaluators/geneval2_result_normalizer.py`
- `src/gen_retry/evaluators/normalizer.py`

实现方式：

- `run_geneval2_single_image.py` 可对单张图调用 `../GenEval2/evaluation.py`，默认 method 为 `soft_tifa_gm`。
- 该脚本默认使用本地 `Qwen3-VL-8B-Instruct` 路径作为 GenEval2 verifier model。
- `Geneval2Adapter` 支持 command template 运行评估，也支持从 score list 读取。
- GenEval2 atom rows 被归一化为：
  - `score`
  - `passed_constraints`
  - `failed_constraints`
  - `uncertain_constraints`
  - `critical_failure_types`
  - `raw_report`

判断：

- 真实 episode 中已保存结构化 GenEval2 反馈。
- `.geneval2.json` 原始评估输出与 raw episode 内 `eval_report.raw_report.rows` 均可回溯。
- 没有发现独立 Soft-TIFA pipeline；Soft-TIFA-GM 是当前 GenEval2 单图脚本的默认 method。

### Teacher replan

相关文件：

- `src/gen_retry/teachers/gpt55_teacher_adapter.py`
- `src/gen_retry/teachers/seed_teacher_adapter.py`
- `src/gen_retry/prompts/initial_plan_prompt.py`
- `src/gen_retry/prompts/retry_replan_prompt.py`
- `src/gen_retry/schemas/actions.py`

实现方式：

- teacher 支持 OpenAI-compatible chat completions，通过以下环境变量配置：
  - `GEN_RETRY_TEACHER_BASE_URL`
  - `GEN_RETRY_TEACHER_API_KEY`
  - `GEN_RETRY_TEACHER_MODEL`
  - `GEN_RETRY_TEACHER_TIMEOUT`
  - `GEN_RETRY_TEACHER_MAX_RETRIES`
- `initial_plan` 输出 schema：
  - `parsed_constraints`
  - `selected_skills`
  - `generation_strategy`
  - `initial_prompt`
  - `generation_guards`
- `retry_replan` 输入包含：
  - `original_prompt`
  - `previous_initial_plan`
  - `previous_prompt`
  - `previous_selected_skills`
  - `normalized_eval_report`
  - `retry_history`
  - `retry_round`
  - `retry_budget_left`
  - `evaluator_type`
- `retry_replan` 输出 schema：
  - `decision: regenerate`
  - `failure_types`
  - `diagnosis`
  - `previous_plan_error`
  - `skill_revision`
  - `preserve_constraints`
  - `repair_constraints`
  - `regeneration_strategy`
  - `retry_prompt`
  - `expected_improvement`
  - `regression_risks`

判断：

- teacher 确实看到结构化反馈和 compact retry history。
- teacher 看到的是归一化文本/JSON 反馈，不看图像内容本身。
- 没有显式 `best_so_far` 对象；best score/image 只能从 `retry_history` 间接推断。
- 多轮 retry 时，state 没有完整传入上一轮 `RetryReplanAction`，只传 `previous_prompt`、`previous_selected_skills`、`retry_history` 摘要。

### Retry generation

相关文件：

- `src/gen_retry/collectors/collect_episodes.py`
- `src/gen_retry/schemas/actions.py`

实现方式：

- retry 只允许 `decision: regenerate`。
- `RetryReplanAction.validate()` 明确禁止 direct image edit 相关字段，如 `edit_instruction`、`mask`、`bbox`、`inpaint`。
- collector 使用 `action.retry_prompt` 再次调用同一个 generator。
- `--max-retry` 默认 2，主真实集 metadata 显示 `max_retry: 2`。

判断：

- retry generation 确实使用 teacher replan 输出的 `retry_prompt`。
- 当前不是 image editing trajectory，也不是 tool/plugin 调用真实外部 skill；skill 主要是 planner schema 中的诊断标签和提示策略。

### Trajectory storage

相关文件：

- `src/gen_retry/schemas/episode.py`
- `src/gen_retry/collectors/collect_episodes.py`
- `data/raw_episodes*/*.json`

当前 raw episode 保存：

- `episode_id`
- `original_prompt`
- `evaluator_type`
- `generator_name`
- `teacher_name`
- `initial_plan`
- `attempts[]`
  - `round`
  - `prompt_used`
  - `image_path`
  - `eval_report`
  - `planner_action`
  - `metadata`
- `stop_rule_result`
- `final_outcome`
- `metadata`

判断：

- raw episode 能保存 prompt、action、image path、evaluator feedback、score、teacher decision/replan、retry history。
- 没有单独稳定的 `image_id` 字段，当前主要用 `image_path` 充当引用。
- 主真实集 schema validation error 数为 0，missing field count 为 0。

### SFT conversion

相关文件：

- `scripts/export_sft.py`
- `src/gen_retry/export/export_sft.py`
- `src/gen_retry/filters/filter_sft_samples.py`
- `scripts/validate_tool_sft.py`

导出格式：

- compact step-level SFT：
  - `initial_plan_sft`
  - `retry_replan_sft`
  - ShareGPT-like `messages`: system/user/assistant
  - assistant target 是完整 JSON action，不只是 final prompt rewrite。
- tool trajectory SFT：
  - 一条 episode 一个 row。
  - 伪工具调用包括 `query_skill`、`generate_image`、`judge_image`。
  - metadata 标出 trainable/non-trainable message indices。

过滤逻辑：

- `retry_replan` compact row 只接受：
  - `passed_after_retry`
  - `improved_after_retry`
  - 或 `failed_after_budget` 但至少有改善且无新 critical failure
- 拒绝：
  - direct image edit action
  - invalid skill
  - no improvement
  - regressed
  - failure type 与 action 不一致

判断：

- SFT target 是决策/动作 JSON，而不是简单 prompt rewrite。
- compact SFT 会过滤低价值 retry。
- tool trajectory 会保留完整轨迹，但其中 final `<submit>`/`stop` 也是 trainable assistant message；是否训练 stop 需要按训练目标再确认。

## 2. 当前数据统计

### 主真实闭环集：`data/raw_episodes_real_hard_atom090_next20`

| 指标 | 数值 |
|---|---:|
| prompts / episodes | 20 |
| 初始生成数 | 20 |
| 初始失败图 | 5 |
| 初始通过图 | 15 |
| retry episodes | 5 |
| retry attempts | 7 |
| retry 后成功轨迹 | 3 |
| improved-but-not-passed 轨迹 | 0 |
| no-improvement 轨迹 | 0 |
| regressed 轨迹 | 2 |
| 平均 retry rounds / episode | 0.35 |
| 初始平均分 | 0.9541 |
| 最终平均分 | 0.9730 |
| retry episode 的 retry 前平均分 | 0.8173 |
| retry episode 的 retry 后最终平均分 | 0.8932 |
| 初始 pass rate | 75% |
| 最终 pass rate | 90% |
| generator | `gpt_image2` |
| teacher | `gpt55` |
| evaluator | `geneval2` |
| validation errors | 0 |

主真实集的初始失败类型分布：

| failure type | count |
|---|---:|
| `count_mismatch` | 6 |
| `relation_mismatch` | 1 |

主真实集的 retry transition count：

| transition | count |
|---|---:|
| `passed_after_retry` | 3 |
| `improved_after_retry` | 1 |
| `regressed` | 3 |

说明：这里的 failure type count 是 failed constraint count，不是 episode count。一个 episode 可包含多个 failed constraints。

### 其他真实/半真实 episode 集

| 目录 | episodes | 初始失败 | retry attempts | final outcomes | 备注 |
|---|---:|---:|---:|---|---|
| `data/raw_episodes_real_smoke` | 3 | 1 | 1 | 2 pass without retry, 1 passed after retry | 真实 `gpt_image2` + GenEval2 smoke |
| `data/raw_episodes_real_smoke_atom090` | 3 | 0 | 0 | 3 pass without retry | 没有 retry 样本 |
| `data/raw_episodes_real_static_smoke_5` | 5 | 0 | 0 | 5 pass without retry | 没有 retry 样本 |
| `data/raw_episodes_real_hard_smoke_5` | 4 | 1 | 2 | 3 pass without retry, 1 regressed | 小批量 hard smoke |
| `data/raw_episodes_real_hard_smoke_atom090_5` | 5 | 1 | 2 | 4 pass without retry, 1 regressed | 小批量 hard smoke |
| `data/raw_episodes/geneval2_gpt55_smoke` | 3 | 3 | 3 | 3 passed after retry | mock generator/evaluator feedback，不能代表真实图像分布 |
| `data/raw_episodes` | 5 | 5 | 5 | 5 passed after retry | mock Geneval pipeline |

### SFT 导出统计

| 文件 | rows | sample types | 说明 |
|---|---:|---|---|
| `data/sft/retry_sft_real_hard_atom090_next20_compact.jsonl` | 23 | 20 `initial_plan`, 3 `retry_replan` | 主真实集 compact SFT |
| `data/sft/retry_sft_real_hard_atom090_next20_tool.jsonl` | 20 | 20 `tool_trajectory` | 主真实集完整 tool 轨迹 |
| `data/rejected/retry_replan_real_hard_atom090_next20_rejected.jsonl` | 4 | 4 rejected `retry_replan` | 主要因 regressed 被拒绝 |
| `data/sft/retry_sft_real_smoke.jsonl` | 4 | 3 `initial_plan`, 1 `retry_replan` | smoke |
| `data/sft/retry_sft_real_smoke_atom090_compact.jsonl` | 3 | 3 `initial_plan` | 无 retry |
| `data/sft/retry_sft_real_static_smoke_5.jsonl` | 5 | 5 `initial_plan` | 无 retry |
| `data/sft/geneval2_gpt55_smoke_sharegpt.jsonl` | 6 | 3 `initial_plan`, 3 `retry_replan` | mock generator/evaluator |

判断：

- 主真实 compact SFT 中 retry row 仅 3 条，远低于训练一个 retry agent 所需规模。
- 当前 compact SFT 中 initial_plan row 明显多于 retry_replan row。
- tool trajectory row 数等于 episode 数，但 pass-without-retry episode 占比高。

### 图像与评估 sidecars

主真实集 `data/images/real_hard_atom090_next20`：

- `.png`: 27
- `.png.json`: 27
- `.geneval2.json`: 27

这与 20 个初始 attempt + 7 个 retry attempt 对齐。

## 3. Current implementation vs Intended strategy

| 维度 | Current implementation | Intended strategy | 结论 |
|---|---|---|---|
| pilot prompt 数 | 最大真实闭环集 20 prompts；已有若干 GenEval2 prompt 子集但未全部闭环生成 | 100-200 prompts | 不满足 |
| prompt 来源 | GenEval2 子集为主，也有 custom/mock prompt | GenEval2-style prompt pilot | 部分满足 |
| 初始图数量 | 每 prompt 1 张，API payload `n: 1` | 每 prompt 4-5 张初始图/seeds | 不满足 |
| 初始 generator | 实际真实数据为 `gpt_image2` | 后续 RL 中同一 target generator | 对齐性 unknown，当前没有证据 |
| evaluator | GenEval2/Soft-TIFA-GM 单图评估 + 结构化归一化 | GenEval2-style structured evaluation | 基本满足 |
| feedback 字段 | score、passed/failed/uncertain constraints、critical failure types、raw rows | 结构化诊断反馈 | 基本满足 |
| teacher 输入 | original prompt、previous plan/prompt/skills、normalized report、retry history、retry budget | original prompt + previous action + structured feedback + compact memory/best-so-far | 部分满足；缺 explicit best-so-far 和完整 previous retry action |
| teacher 输出 | structured `retry_replan` JSON action | structured retry decision/action | 基本满足 |
| skill/tool 调用 | schema 中选择/修订 skills；tool SFT 中有 synthetic `query_skill` | call appropriate skill/tool | 部分满足；运行时不是实际外部 skill 调用 |
| retry execution | 同一 generator 用 `retry_prompt` 重生成 | target generator execute retry | 机制满足，但 target generator 对齐 unknown |
| retry rounds | `max_retry` 默认 2 | 2-3 rounds | 满足 |
| stop rule | pass/no failed/budget；最终标记 regressed/improved | pass、max retry、no improvement、large regression | 部分满足；缺 no-improvement/regression 早停 |
| high-value trajectory filter | compact retry SFT 过滤 regressed/no improvement | 只保留 failure -> feedback -> teacher replan -> retry -> pass/clear improvement | 基本满足，但样本太少 |
| SFT target | JSON action，含 diagnosis、skills、preserve/repair、retry_prompt | next-action prediction | 满足 |
| 数据分布 | pass-without-retry 多，retry row 少 | failure/retry states 足够 | 不满足 |

## 4. 关键 mismatch / 风险

### 1. Teacher/generator 太强，失败状态太少

主真实集初始 pass rate 为 75%，其他真实 smoke/static 集甚至 100% pass-without-retry。`gpt-5.5` 先做强 initial plan，再用 `gpt-image-2` 生成，导致有效失败/retry 状态明显不足。

风险：

- SFT 会学到大量 initial planning，但学不到足够的诊断驱动 retry。
- 失败样本可能集中在少数难例，泛化差。

### 2. 轨迹环境与后续 RL target generator 的对齐性不明确

当前真实生成器是 `gpt_image2`。仓库里没有证据说明后续 RL 也会使用同一个 generator，也没有当前闭环中使用 Qwen3-VL-4B-Instruct 作为 agent 或 generator 的实现。

风险：

- 如果后续 RL 的生成器更弱或失败模式不同，当前 retry action 分布会错配。
- 当前 SFT 可能学到对 `gpt-image-2` 有效的 prompt 修补，而不是目标环境下的控制策略。

### 3. Teacher context 还不够 agent-like

已有上下文包含 structured feedback 和 retry history，但缺少：

- explicit `best_so_far` attempt。
- best score / best image ref。
- 完整 previous retry action。
- 当前图像内容或图像引用给 teacher 的可见通道。
- 明确的 failure persistence / newly fixed / newly broken 对比字段。

风险：

- 多轮 retry 中 teacher 只能从摘要推断状态，难以做真正的 memory-aware policy。

### 4. pass cases 和 initial_plan rows 占比过高

主真实 compact SFT 为 23 rows，其中 20 条是 `initial_plan`，只有 3 条是 `retry_replan`。tool trajectory 也包含大量 pass-without-retry episode。

风险：

- 如果直接混训，会偏向“生成初始好 prompt”或“直接提交/停止”，而不是从失败诊断中修复。

### 5. 真实 failure type 覆盖不足

主真实集初始失败只有：

- `count_mismatch`: 6 failed constraints
- `relation_mismatch`: 1 failed constraint

没有足够真实样本覆盖：

- object missing / extra object
- color mismatch
- attribute/material mismatch
- spatial/position mismatch
- 多约束同时失败
- repair 后 preserve 已通过约束的回归案例

风险：

- SFT 不足以训练完整 GenEval2 feedback-driven retry agent。

### 6. retry 轨迹改善不稳定

主真实集 5 条初始失败 episode：

- 3 条最终 `passed_after_retry`
- 2 条最终 `regressed`
- 7 次 retry attempts 中有 3 次 transition 为 `regressed`

虽然 retried episodes 的平均最终分从 0.8173 到 0.8932，但回归比例仍高。

风险：

- 如果 tool trajectory 未过滤，模型可能看到 noisy loops。
- compact SFT 过滤掉 regressed 后只剩 3 条 retry row，规模不足。

### 7. stop rule 不完整

`should_continue()` 目前按以下规则停止：

- no failed constraints
- score threshold without critical failure
- retry budget exhausted

它会记录 `regressed` 和 `no_improvement` transition，但没有显式 large regression / no improvement 早停。

风险：

- 轨迹可能继续执行低价值 retry。
- 与预期策略中的 stop by no improvement / regression-too-large 不完全一致。

## 5. Top 5 gaps before SFT

1. **真实 retry 样本数太少**：主真实 compact SFT 只有 3 条高价值 retry_replan row。
2. **缺少 4-5 初始候选图/seeds**：无法从同一 prompt 的多失败状态中构造丰富轨迹。
3. **generator alignment unknown**：当前 `gpt_image2` 是否等于后续 RL target generator 未证明。
4. **failure type coverage 不足**：真实失败主要是 count/relation，缺 object/color/attribute/spatial 多样性。
5. **stop/memory 机制不完整**：没有 explicit best-so-far、no-improvement 早停、large-regression 早停。

## 6. Top 5 next implementation steps

1. **实现并运行 100-200 prompt pilot**：优先使用 `geneval2_static_retry_candidates_25`、`position_20`、`verb_20`、`hard_30` 等组合，按 failure bucket 平衡采样。
2. **增加 `images_per_prompt` / `seed` / `candidate_id`**：每个 prompt 生成 4-5 初始图，并把每张图作为独立 candidate trajectory 起点。
3. **确认 target generator 并复用到 initial/retry**：如果后续 RL 不用 `gpt_image2`，应尽快切到目标 generator 或至少并行采集 target-generator failures。
4. **增强 retry state memory**：加入 `best_so_far`、`last_action`、`fixed_constraints`、`persistent_failures`、`new_failures`、`score_delta_from_best`。
5. **建立数据筛选与平衡脚本**：按 failure type、transition outcome、score delta、regression risk、prompt skill bucket 选择 SFT 样本，并限制 pass-without-retry/initial_plan 占比。

## 7. 建议的 cleaned trajectory JSON schema

建议把 raw episode schema 稳定为 candidate-level，而不是 prompt-level：

```json
{
  "trajectory_id": "string",
  "prompt_id": "string",
  "candidate_id": "string",
  "source": {
    "dataset": "geneval2",
    "source_index": 0,
    "prompt": "string",
    "skills": ["count", "attribute"],
    "atom_count": 0,
    "vqa_list": []
  },
  "environment": {
    "generator_name": "string",
    "generator_model": "string",
    "evaluator_name": "geneval2",
    "evaluator_method": "soft_tifa_gm",
    "teacher_name": "gpt55",
    "max_retry": 2,
    "pass_threshold": 0.95,
    "atom_threshold": 0.9
  },
  "attempts": [
    {
      "round": 0,
      "attempt_type": "initial_generation",
      "action": {
        "action_type": "initial_plan",
        "selected_skills": [],
        "initial_prompt": ""
      },
      "generation": {
        "prompt_used": "",
        "seed": null,
        "image_id": "attempt_0",
        "image_path": "",
        "generator_metadata_path": ""
      },
      "evaluation": {
        "score": 0.0,
        "passed": false,
        "passed_constraints": [],
        "failed_constraints": [],
        "uncertain_constraints": [],
        "critical_failure_types": [],
        "raw_eval_path": ""
      },
      "transition": {
        "from_round": null,
        "outcome": "initial",
        "score_delta": null,
        "fixed_constraints": [],
        "persistent_failures": [],
        "new_failures": []
      }
    }
  ],
  "memory": {
    "best_round": 0,
    "best_score": 0.0,
    "best_image_id": "attempt_0",
    "best_failed_constraints": [],
    "retry_history_summary": ""
  },
  "stop": {
    "stopped": true,
    "reason": "passed|max_retry|no_improvement|large_regression",
    "passed": false
  },
  "final_outcome": "passed_after_retry|improved_after_retry|failed_after_budget|regressed"
}
```

## 8. 建议的 step-level SFT sample format

建议把训练目标限定为下一步 agent action，且显式区分可训练 assistant action 与不可训练 tool/evaluator context。

```json
{
  "sample_id": "string",
  "trajectory_id": "string",
  "sample_type": "retry_replan",
  "input": {
    "original_prompt": "string",
    "current_round": 1,
    "retry_budget_left": 2,
    "previous_action": {
      "action_type": "initial_plan",
      "initial_prompt": "string",
      "selected_skills": []
    },
    "current_eval_report": {
      "score": 0.0,
      "failed_constraints": [],
      "passed_constraints": [],
      "critical_failure_types": []
    },
    "memory": {
      "best_score": 0.0,
      "best_prompt": "string",
      "fixed_constraints": [],
      "persistent_failures": [],
      "new_failures": [],
      "regression_risks": []
    },
    "available_skills": []
  },
  "target": {
    "action_type": "retry_replan",
    "decision": "regenerate",
    "failure_types": [],
    "diagnosis": "string",
    "previous_plan_error": {
      "error_source": "string",
      "details": "string"
    },
    "skill_revision": {
      "previous_skills": [],
      "new_skills": [],
      "reason": "string"
    },
    "preserve_constraints": [],
    "repair_constraints": [],
    "regeneration_strategy": "string",
    "retry_prompt": "string",
    "expected_improvement": [],
    "regression_risks": []
  },
  "labels": {
    "train": true,
    "value_class": "passed_after_retry|clear_improvement",
    "failure_type_bucket": "count|object|attribute|spatial|relation|multi"
  }
}
```

训练建议：

- `initial_plan` 和 `retry_replan` 分开配比。
- retry SFT 优先使用 `failure -> feedback -> teacher replan -> retry -> pass/clear improvement`。
- pass-without-retry 只用于少量 initial planning 或 stop calibration，不应主导 retry policy。
- regressed/no-improvement trajectory 可保留为 analysis/eval，不建议直接作为正向 SFT target。

## 9. Unknown / 需要补充证据

- 后续 RL 的 target generator 是什么，目前仓库没有明确证据。
- 是否要让 Qwen3-VL-4B-Instruct 学完整 controller，还是只学 `retry_replan` macro-action，目前需要训练方案确认。
- API raw logs 位于 ignored path，不作为本次审计依据。
- 当前统计基于已有 JSON/JSONL 文件；未重新运行真实 API、GenEval2 或训练。
- `data/raw_episodes_real_hard_smoke_5` 目录只有 4 个 episode 文件，缺第 5 条的原因需查 collector error log 或运行记录。

