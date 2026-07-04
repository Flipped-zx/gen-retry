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
- 新增 100 条 first-pass ingest 入口：`scripts/build_geneval2_retry_packages.py` 可将 Qwen generation manifest、initial plan cache、可选 GenEval2 normalized report 合并为 offline generation packages。
- 新增 100 条 first-pass retry plan 批处理入口：`scripts/build_geneval2_retry_plans.py` 可在 GenEval2 诊断回传后一键 rebuild package、调用 teacher、写 retry action manifest/failure summary。
- retry action package 现在持久化 `teacher_request`，用于审计 teacher API 实际看到的诊断和历史 context。
- teacher batch 会自动写 `retry_plan_quality_report.json`，并可用 `scripts/check_retry_plan_quality.py` 独立复查 retry plan 是否覆盖 failed constraints、preserve passed constraints、调用正确技能、避免 raw image upload/direct edit。
- 新增 retry 输入 preflight：`scripts/check_geneval2_retry_inputs.py` 会在 teacher API 前检查 100 条 package、diagnostic job、normalized eval report 的 candidate_id 覆盖是否完全一致，并确认 teacher 不需要 raw image bytes。

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

## 2.1 当前 100 条 first-pass checkpoint

当前本仓库已有：

- `data/qwen_geneval2_balanced_100_x5_initial_gpt55_a100/generation_manifest.jsonl`：100 个 prompt x 5 candidates。
- `data/plans/initial/geneval2_balanced_100_gpt55/`：100 个 initial plan cache。
- `data/incoming_generation_results/geneval2_balanced_100_round0_initial_gpt55/`：已从 manifest 生成的 100 个 round-0 generation packages，默认使用 `candidate_index=0`。
- `data/geneval2_jobs/balanced100_candidate0/`：已生成的 100 张 candidate-0 诊断作业输入，不会启动 GenEval2。

构建命令：

```bash
python3 scripts/build_geneval2_retry_packages.py \
  --manifest data/qwen_geneval2_balanced_100_x5_initial_gpt55_a100/generation_manifest.jsonl \
  --output-dir data/incoming_generation_results/geneval2_balanced_100_round0_initial_gpt55 \
  --initial-plan-dir data/plans/initial/geneval2_balanced_100_gpt55 \
  --candidate-index 0 \
  --limit 100 \
  --require-initial-plan
```

如果 GenEval2 诊断已经在另一台机器跑完，先把 normalized result JSON/JSONL 复制到本机，然后重新构建 package 并附上诊断：

如果另一台机器回传的是 official `raw_score_lists.json`，先用本机保存的 `eval_benchmark.jsonl` 归一化为 candidate-level reports：

```bash
python3 scripts/normalize_geneval2_results.py \
  --input data/geneval2_jobs/balanced100_candidate0/raw_score_lists.json \
  --benchmark-data data/geneval2_jobs/balanced100_candidate0/eval_benchmark.jsonl \
  --aggregate-by candidate_id \
  --atom-threshold 0.9 \
  --output data/geneval2_jobs/balanced100_candidate0/normalized_reports.jsonl
```

`eval_benchmark.jsonl` 包含 `candidate_id`，normalizer 会把它继承到每个 atom row，并输出可直接用于 package builder 和 preflight 的 `candidate_id` 字段。

推荐使用 prepare 脚本把“归一化诊断、重建带 eval 的 packages、三方 preflight”收成一个无 API checkpoint：

```bash
python3 scripts/prepare_geneval2_retry_inputs.py \
  --manifest data/qwen_geneval2_balanced_100_x5_initial_gpt55_a100/generation_manifest.jsonl \
  --package-dir data/incoming_generation_results/geneval2_balanced_100_round0_with_eval \
  --initial-plan-dir data/plans/initial/geneval2_balanced_100_gpt55 \
  --diagnostic-jobs data/geneval2_jobs/balanced100_candidate0/diagnostic_jobs.jsonl \
  --raw-score-lists data/geneval2_jobs/balanced100_candidate0/raw_score_lists.json \
  --benchmark-data data/geneval2_jobs/balanced100_candidate0/eval_benchmark.jsonl \
  --candidate-index 0 \
  --limit 100
```

如果已经有 `normalized_reports.jsonl`，把 `--raw-score-lists ... --benchmark-data ...` 换成：

```bash
  --eval-results data/geneval2_jobs/balanced100_candidate0/normalized_reports.jsonl
```

prepare 成功时 `prepare_summary.json` 的 `status` 为 `ready_for_teacher`。这个阶段不调用 teacher API。

在真正调用 GPT teacher 前，可以先导出 teacher 将看到的 JSON request 供人工抽查：

```bash
python3 scripts/preview_geneval2_teacher_requests.py \
  --package-dir data/incoming_generation_results/geneval2_balanced_100_round0_with_eval \
  --output data/geneval2_jobs/balanced100_candidate0/teacher_requests_preview.jsonl \
  --summary-output data/geneval2_jobs/balanced100_candidate0/teacher_requests_preview_summary.json
```

preview 复用真实 planner 的 memory、stop rule 和 teacher-state 构造逻辑，但不会调用 API。summary 会标出是否出现 `image_bytes`、`image_url`、`input_image` 等 raw image upload 字段。

```bash
python3 scripts/build_geneval2_retry_packages.py \
  --manifest data/qwen_geneval2_balanced_100_x5_initial_gpt55_a100/generation_manifest.jsonl \
  --output-dir data/incoming_generation_results/geneval2_balanced_100_round0_with_eval \
  --initial-plan-dir data/plans/initial/geneval2_balanced_100_gpt55 \
  --eval-results data/geneval2_jobs/balanced100_candidate0/normalized_reports.jsonl \
  --aggregate-by candidate_id \
  --candidate-index 0 \
  --limit 100 \
  --require-initial-plan
```

调用 teacher API 之前，建议先做输入 preflight。它会检查 package manifest、诊断作业和 normalized reports 是否都是同一批 100 个 `candidate_id`：

```bash
python3 scripts/check_geneval2_retry_inputs.py \
  --package-manifest data/incoming_generation_results/geneval2_balanced_100_round0_with_eval/package_manifest.jsonl \
  --diagnostic-jobs data/geneval2_jobs/balanced100_candidate0/diagnostic_jobs.jsonl \
  --eval-results data/geneval2_jobs/balanced100_candidate0/normalized_reports.jsonl \
  --expected-count 100 \
  --output data/geneval2_jobs/balanced100_candidate0/retry_input_preflight.json
```

诊断回传后，推荐直接用一条命令 rebuild package 并调用 teacher retry planner：

```bash
python3 scripts/build_geneval2_retry_plans.py \
  --manifest data/qwen_geneval2_balanced_100_x5_initial_gpt55_a100/generation_manifest.jsonl \
  --package-dir data/incoming_generation_results/geneval2_balanced_100_round0_with_eval \
  --output-dir data/outgoing_retry_actions/geneval2_balanced_100_round0_gpt55 \
  --trajectory-dir data/raw_trajectories/geneval2_balanced_100_round0_gpt55 \
  --initial-plan-dir data/plans/initial/geneval2_balanced_100_gpt55 \
  --eval-results data/geneval2_jobs/balanced100_candidate0/normalized_reports.jsonl \
  --diagnostic-jobs data/geneval2_jobs/balanced100_candidate0/diagnostic_jobs.jsonl \
  --aggregate-by candidate_id \
  --candidate-index 0 \
  --limit 100 \
  --teacher gpt55 \
  --max-retry 3
```

本地结构验证可以先把 `--teacher gpt55` 改成 `--teacher mock`，不会调用 API。真实 teacher 使用 OpenAI-compatible chat completions，并从 `GEN_RETRY_TEACHER_*` 环境变量读取配置。GPT teacher adapter 会先校验 JSON schema；对 `retry_replan` 还会检查是否覆盖当前 failed constraints、preserve passed constraints、并路由到对应 skill。若第一次回复结构合法但漏掉这些关键诊断覆盖，会自动把质量问题反馈给 teacher 再请求一次修正。

如果已经跑过 `prepare_geneval2_retry_inputs.py`，teacher 步骤可以直接消费准备好的 package dir，不需要再次 rebuild：

```bash
python3 scripts/build_geneval2_retry_plans.py \
  --package-dir data/incoming_generation_results/geneval2_balanced_100_round0_with_eval \
  --output-dir data/outgoing_retry_actions/geneval2_balanced_100_round0_gpt55 \
  --trajectory-dir data/raw_trajectories/geneval2_balanced_100_round0_gpt55 \
  --eval-results data/geneval2_jobs/balanced100_candidate0/normalized_reports.jsonl \
  --diagnostic-jobs data/geneval2_jobs/balanced100_candidate0/diagnostic_jobs.jsonl \
  --limit 100 \
  --teacher gpt55 \
  --max-retry 3
```

Teacher batch 输出：

```text
data/outgoing_retry_actions/geneval2_balanced_100_round0_gpt55/
  retry_action_manifest.jsonl
  batch_summary.json
  batch_failures.jsonl
  batch_skipped.jsonl
  retry_input_preflight.json
  retry_plan_quality_report.json
```

`build_geneval2_retry_plans.py` 会自动写 `retry_input_preflight.json`。如果发现缺失、重复、数量不一致、package 缺少 valid `previous_initial_plan`，或 package 没有声明 `teacher_uses_image_bytes=false`，批处理会在调用 teacher API 之前停止。

独立复查质量：

```bash
python3 scripts/check_retry_plan_quality.py \
  data/outgoing_retry_actions/geneval2_balanced_100_round0_gpt55/retry_action_manifest.jsonl \
  --output data/outgoing_retry_actions/geneval2_balanced_100_round0_gpt55/retry_plan_quality_report.json
```

Teacher retry 默认不上传、也不需要读取 raw image bytes。它需要的是 `original_prompt`、`previous_initial_plan`、`previous_prompt`、`normalized_eval_report`、`retry_history`、memory diff 和 available skills。`image_path` 只作为 artifact reference 保存，便于人工抽检、复现或在本机需要运行 GenEval2 时定位图片。

生成 candidate-0 的 GenEval2 诊断作业清单：

```bash
python3 scripts/run_geneval2_batch.py \
  --manifest data/qwen_geneval2_balanced_100_x5_initial_gpt55_a100/generation_manifest.jsonl \
  --output-dir data/geneval2_jobs/balanced100_candidate0 \
  --candidate-index 0 \
  --limit 100 \
  --n-samples 5 \
  --plan-only \
  --keep-eval-inputs
```

这个命令不会运行 verifier，只写：

- `diagnostic_jobs.jsonl`：100 条诊断任务，保留 `candidate_id`、`prompt_id`、original prompt、image path、VQA/skill metadata。
- `eval_benchmark.jsonl`：可供 GenEval2 batch evaluation 使用的 benchmark rows，`prompt` 字段被设置为 `candidate_id` 以便和 image map 对齐。
- `eval_image_paths.json`：`candidate_id -> image_path` map。
- `geneval2_batch_plan.json`：本次诊断计划摘要。

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
    "current_round": 0,
    "best_so_far_round": 0,
    "best_so_far_score": 0.0,
    "best_so_far_image_path": "string",
    "best_so_far_prompt": "string",
    "best_so_far_failed_constraints": [],
    "previous_action": {},
    "fixed_constraints": [],
    "persistent_failures": [],
    "new_failures": [],
    "regressed_constraints": [],
    "score_delta_from_previous": null,
    "score_delta_from_best": 0.0,
    "retry_history_summary": "string"
  },
  "stop": {
    "should_stop": false,
    "reason": "null"
  },
  "teacher_request": {
    "original_prompt": "string",
    "previous_initial_plan": {},
    "previous_action": {},
    "previous_prompt": "string",
    "current_eval_report": {},
    "retry_history": [],
    "memory": {},
    "available_skills": []
  },
  "retry_ready_action": {
    "action_type": "retry_replan"
  },
  "status": "retry_ready",
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

Raw trajectory 按 candidate 记录，而不是只按 prompt 记录。每个 attempt 保存生成、评估，以及产生当前图的 planner action；本轮评估后 planner 产出的下一步 action 保存在 trajectory 顶层。

注意：`attempts[].planner_action` 是产生该图片的 planner action。round 0 是 `initial_plan`；teacher 对本轮评估后产出的下一步动作保存在顶层 `retry_ready_action` / `latest_teacher_action`，不会覆盖 round-0 attempt 的 `planner_action`。

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
      "previous_action": {
        "action_type": "initial_plan"
      },
      "evaluation": {
        "score": 0.0,
        "passed_constraints": [],
        "failed_constraints": [],
        "uncertain_constraints": [],
        "critical_failure_types": []
      },
      "planner_action": {
        "action_type": "initial_plan"
      },
      "transition": {
        "score_delta_from_previous": null,
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
    "current_round": 0,
    "best_so_far_round": 0,
    "best_so_far_score": 0.0,
    "best_so_far_image_path": "string",
    "best_so_far_prompt": "string",
    "best_so_far_failed_constraints": [],
    "previous_action": {
      "action_type": "initial_plan"
    },
    "fixed_constraints": [],
    "persistent_failures": [],
    "new_failures": [],
    "regressed_constraints": [],
    "score_delta_from_previous": null,
    "score_delta_from_best": 0.0,
    "retry_history_summary": "string"
  },
  "retry_ready_action": {},
  "status": "initial_success|retry_ready|error"
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
      "score_delta_from_previous": null,
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

对于离线 candidate-level raw trajectory，可以直接导出 step-level retry SFT：

```bash
python3 scripts/export_offline_retry_sft.py \
  --trajectories-dir data/raw_trajectories/geneval2_balanced_100_round0_gpt55 \
  --output data/sft/geneval2_balanced_100_round0_retry_replan_sft.jsonl \
  --rejected-output data/rejected/geneval2_balanced_100_round0_retry_replan_rejected.jsonl
```

该导出器的输入是 `latest_teacher_request` / `attempts[].teacher_request`，target 是顶层 `retry_ready_action`。默认会从训练输入中移除本地 `image_path`、`image_id`、`raw_eval_path`、`raw_report` 和 raw image/upload 字段；如需审计 artifact reference，可显式加 `--include-image-refs`。

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

如果只想校验 JSON 合同，而图片文件不在本机：

```bash
python3 scripts/validate_offline_retry_package.py \
  --allow-missing-images \
  data/incoming_generation_results/example_round0.json
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
