# 离线 GenEval2 评估到 Teacher Replan 管线

本文档说明当前 `gen-retry` 仓库如何在不做跨机器通信的前提下，消费另一台机器生成的图片结果和 GenEval2 评估结果，产出可复制回生成机器的 `retry_replan` 动作，并维护 candidate-level trajectory memory。

## 1. 当前审计结论

已经存在的能力：

- GenEval2 prompt/metadata 读取与静态 prompt 文件：`scripts/prepare_geneval2_prompts.py`、`data/prompts/geneval2_*.jsonl`。
- GenEval2 结果归一化：`src/gen_retry/evaluators/geneval2_result_normalizer.py` 可将 official score list 或 atom row 归一化为 `NormalizedEvalReport`。
- GPT/Seed/OpenAI-compatible teacher：`src/gen_retry/teachers/gpt55_teacher_adapter.py` 通过 `GEN_RETRY_TEACHER_*` 环境变量调用 chat completions，并要求结构化 JSON。
- `initial_plan` / `retry_replan` schema：`src/gen_retry/schemas/actions.py` 已有严格校验，禁止 direct image edit、mask、bbox、inpaint 等字段。
- raw episode 和 SFT export：`src/gen_retry/schemas/episode.py`、`src/gen_retry/export/export_sft.py` 支持 compact/tool 轨迹导出。

本次补齐的缺口：

- `RetryReplanAction` 新增 `branch_source` 与 `branch_source_round`，显式表达下一轮从 latest 还是 best-so-far 分支。
- Teacher retry 输入新增完整 `previous_action`、`current_eval_report`、`current_round`、显式 `best_so_far`、fixed/persistent/new/regressed constraints、score deltas、available skills。
- 新增离线 planner：`src/gen_retry/offline_planner.py` 和 `scripts/offline_evaluate_and_plan.py`。
- 新增 candidate-level raw trajectory JSON，而不是只按 prompt 记录。
- 新增 rule-based stop：passed、max_retry、no_improvement、large_regression、invalid_teacher_action。
- 新增校验脚本：`scripts/validate_offline_retry_package.py`。
- Compact SFT export 的 retry state 已包含 memory 字段，同时继续避免把本地 `image_path` 泄漏进训练上下文。

## 2. 离线管线如何工作

1. Machine A 使用 `qwen-image-2512` 生成图片，并写出一个 generation package JSON。
2. 将 generation package、图片文件、可选 GenEval2 raw result 文件手动复制到 Machine B。
3. Machine B 运行 `scripts/offline_evaluate_and_plan.py`：
   - 读取 generation package。
   - 如果 package 已带 `evaluation`，直接解析为 `NormalizedEvalReport`。
   - 如果 package 或命令行提供 GenEval2 result path，则读取并归一化。
   - 如果只有 image path 且提供 `--geneval2-command-template`，则调用本地 GenEval2 命令并读取输出。
   - 更新 candidate-level trajectory attempts。
   - 计算 fixed、persistent、new、regressed、score deltas、best-so-far。
   - 先执行 stop rule；未停止时调用 teacher 的 `retry_replan`。
   - 写出 retry action package 和 raw trajectory JSON。
4. 将 Machine B 输出的 retry action package 手动复制回 Machine A。
5. Machine A 使用 `teacher_action.retry_prompt` 生成下一轮图片，并在下一轮 package 的 `previous_action` 中放入完整 `teacher_action`。

## 3. Machine A 到 Machine B 输入 JSON

最小字段如下。`evaluation` 是可选字段；如果不提供，Machine B 必须能通过 raw eval path 或 GenEval2 command 得到评估。

```json
{
  "schema_version": "v1",
  "trajectory_id": "string",
  "prompt_id": "string",
  "candidate_id": "string",
  "round": 0,
  "source": {
    "dataset": "geneval2",
    "source_index": 0,
    "original_prompt": "string",
    "skills": ["count", "attribute", "relation"],
    "atom_count": 0,
    "vqa_list": []
  },
  "generation": {
    "generator_name": "qwen-image-2512",
    "prompt_used": "string",
    "seed": 0,
    "image_path": "string",
    "image_id": "string",
    "generation_metadata": {}
  },
  "evaluation": {
    "score": 0.0,
    "passed_constraints": [],
    "failed_constraints": [],
    "uncertain_constraints": [],
    "critical_failure_types": [],
    "raw_eval_path": "string"
  },
  "previous_action": null,
  "retry_history": []
}
```

`previous_action` 在 round 0 为 `null`。从 round 1 开始，它应是上一轮 Machine B 输出的完整 `teacher_action`，不能只传 prompt 或 skill 名称。

## 4. Machine B 到 Machine A 输出 JSON

Machine A 主要读取 `teacher_action.retry_prompt`。如果 `stop.should_stop=true`，则不应继续生成下一轮。

```json
{
  "schema_version": "v1",
  "trajectory_id": "string",
  "prompt_id": "string",
  "candidate_id": "string",
  "round": 0,
  "evaluation": {
    "score": 0.0,
    "passed": false,
    "passed_constraints": [],
    "failed_constraints": [],
    "uncertain_constraints": [],
    "critical_failure_types": [],
    "raw_eval_path": "string",
    "raw_report": {}
  },
  "memory": {
    "best_so_far_round": 0,
    "best_so_far_score": 0.0,
    "best_so_far_image_path": "string",
    "best_so_far_prompt": "string",
    "best_so_far_failed_constraints": [],
    "fixed_constraints": [],
    "persistent_failures": [],
    "new_failures": [],
    "regressed_constraints": [],
    "score_delta_from_previous": 0.0,
    "score_delta_from_best": 0.0,
    "retry_history_summary": "string"
  },
  "stop": {
    "should_stop": false,
    "reason": "null"
  },
  "teacher_action": {
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
    "regression_risks": [],
    "branch_source_round": 0,
    "branch_source": "latest"
  },
  "trajectory_path": "data/raw_trajectories/..."
}
```

`stop.reason` 只使用：`passed`、`max_retry`、`no_improvement`、`large_regression`、`invalid_teacher_action`、`null`。

## 5. Raw Trajectory JSON

Raw trajectory 按 candidate 记录，而不是只按 prompt 记录。每个 attempt 保存生成、评估、产生当前图的上一轮 action，以及本轮评估后 planner 产出的下一步 action。

```json
{
  "schema_version": "v1",
  "trajectory_id": "string",
  "prompt_id": "string",
  "candidate_id": "string",
  "source": {},
  "generator_name": "qwen-image-2512",
  "initial_plan": {},
  "attempts": [
    {
      "round": 0,
      "attempt_type": "initial_generation",
      "generation": {
        "generator_name": "qwen-image-2512",
        "prompt_used": "string",
        "seed": 0,
        "image_id": "string",
        "image_path": "string",
        "generation_metadata": {}
      },
      "previous_action": {},
      "evaluation": {
        "score": 0.0,
        "passed_constraints": [],
        "failed_constraints": [],
        "uncertain_constraints": [],
        "critical_failure_types": []
      },
      "planner_action": {},
      "transition": {
        "score_delta_from_previous": 0.0,
        "score_delta_from_best": 0.0,
        "fixed_constraints": [],
        "persistent_failures": [],
        "new_failures": [],
        "regressed_constraints": [],
        "transition_type": "initial"
      }
    }
  ],
  "memory": {
    "best_so_far_round": 0,
    "best_so_far_score": 0.0,
    "best_so_far_image_path": "string",
    "best_so_far_prompt": "string",
    "best_so_far_failed_constraints": [],
    "retry_history_summary": "string"
  }
}
```

## 6. Step-Level SFT Schema

Retry SFT 的输入侧现在包含完整 memory；target 是结构化 `retry_replan`，不是自由文本 prompt rewrite。

```json
{
  "input": {
    "original_prompt": "string",
    "current_round": 1,
    "retry_budget_left": 2,
    "previous_initial_plan": {},
    "previous_action": {},
    "previous_prompt": "string",
    "current_eval_report": {},
    "retry_history": [],
    "memory": {
      "best_so_far": {},
      "fixed_constraints": [],
      "persistent_failures": [],
      "new_failures": [],
      "regressed_constraints": [],
      "score_delta_from_previous": 0.0,
      "score_delta_from_best": 0.0
    },
    "available_skills": []
  },
  "target": {
    "action_type": "retry_replan",
    "decision": "regenerate",
    "failure_types": [],
    "diagnosis": "string",
    "skill_revision": {},
    "preserve_constraints": [],
    "repair_constraints": [],
    "regeneration_strategy": "string",
    "retry_prompt": "string",
    "expected_improvement": [],
    "regression_risks": [],
    "branch_source": "latest"
  }
}
```

## 7. 命令示例

处理单个 package，使用已嵌入或已指定的 GenEval2 结果：

```bash
python3 scripts/offline_evaluate_and_plan.py \
  --input data/incoming_generation_results/example_round0.json \
  --output-dir data/outgoing_retry_actions \
  --trajectory-dir data/raw_trajectories \
  --max-retry 3 \
  --teacher gpt55 \
  --evaluator geneval2
```

处理一个目录：

```bash
python3 scripts/offline_evaluate_and_plan.py \
  --input 'data/incoming_generation_results/*.json' \
  --output-dir data/outgoing_retry_actions \
  --trajectory-dir data/raw_trajectories \
  --max-retry 3 \
  --teacher gpt55 \
  --evaluator geneval2
```

从已有 raw trajectory 恢复：

```bash
python3 scripts/offline_evaluate_and_plan.py \
  --input data/incoming_generation_results/traj_001_candidate_a_round1.json \
  --resume-trajectory data/raw_trajectories/traj_001__candidate_a.json \
  --output-dir data/outgoing_retry_actions \
  --max-retry 3 \
  --teacher gpt55
```

本地无 API key 时可用 mock teacher 做结构验证：

```bash
python3 scripts/offline_evaluate_and_plan.py \
  --input data/incoming_generation_results/example_round0.json \
  --output-dir data/outgoing_retry_actions \
  --trajectory-dir data/raw_trajectories \
  --teacher mock
```

如果 package 只有 image path，没有 eval：

```bash
python3 scripts/offline_evaluate_and_plan.py \
  --input data/incoming_generation_results/example_round0.json \
  --geneval2-command-template 'python /path/to/geneval2/evaluate.py --image {image_path_raw} --prompt {prompt_raw} --output {output_path_raw}' \
  --output-dir data/outgoing_retry_actions \
  --teacher gpt55
```

## 8. 校验命令

校验 Machine A 输入、Machine B 输出或 raw trajectory：

```bash
python3 scripts/validate_offline_retry_package.py \
  data/incoming_generation_results/example_round0.json \
  data/outgoing_retry_actions/traj_001__candidate_a__round_0_retry_action_package.json \
  data/raw_trajectories/traj_001__candidate_a.json
```

校验内容包括：

- required fields 是否存在；
- image path 是否存在；
- eval report 是否可解析为 `NormalizedEvalReport`；
- raw trajectory 的 best-so-far 是否可重新计算并一致；
- fixed、new、persistent、regressed constraints 是否和相邻 round diff 一致；
- `teacher_action` 是否是合法 JSON action；
- `stop.should_stop=false` 时是否存在非空 `teacher_action.retry_prompt`。

## 9. 配置与限制

Teacher API 仍通过环境变量配置，不写死 key：

- `GEN_RETRY_TEACHER_BASE_URL`
- `GEN_RETRY_TEACHER_API_KEY`
- `GEN_RETRY_TEACHER_MODEL`
- `GEN_RETRY_TEACHER_TIMEOUT`
- `GEN_RETRY_TEACHER_MAX_RETRIES`

本阶段没有实现：

- RPC、自动跨机器同步、文件监听或远程传输；
- 训练、RL、批量大规模生成；
- 自动 Qwen-Image-2512 调用；
- 自动上传或下载图片。

当前实现适合后续 pilot：100 个 GenEval2 prompt，每个 prompt 4-5 个初始 candidate，`max_retry=3`。
