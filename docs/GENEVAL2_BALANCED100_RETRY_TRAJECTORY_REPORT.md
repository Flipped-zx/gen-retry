# GenEval2 Balanced-100 初始生成诊断与 Retry Trajectory 报告

## 结论摘要

- 当前状态：`retry_ready`。
- prompts: 100；manifest rows: 500；selected all candidate images: 500。
- 本地存在初始图片：500 / 500；selected 图片：500 / 500。
- initial plan files: 100；generation packages: 500；diagnostic jobs: 500。
- GenEval2 eval reports: 500 
- pass before retry: 29；fail before retry: 471；pass rate: 5.80%。
- raw trajectories: 500；`initial_success`: 29；`retry_ready`: 471；valid teacher retry plans: 471 

## 1. 数据位置与可用性

| artifact | path | exists | count |
|---|---|---:|---:|
| selected prompts | `data/prompts/geneval2_balanced_100.jsonl` | yes | 100 |
| initial plan cache | `data/plans/initial/geneval2_balanced_100_gpt55` | yes | 100 |
| Qwen initial generation manifest | `data/qwen_geneval2_balanced_100_x5_initial_gpt55_a100/generation_manifest.jsonl` | yes | 500 |
| generation packages | `data/incoming_generation_results/geneval2_balanced_100x5_round0_with_eval/package_manifest.jsonl` | yes | 500 |
| GenEval2 diagnostic jobs | `data/geneval2_jobs/balanced100_all_candidates/diagnostic_jobs.jsonl` | yes | 500 |
| normalized GenEval2 reports | `data/geneval2_jobs/balanced100_all_candidates/normalized_reports.jsonl` | yes | 500 |
| retry action manifest | `data/outgoing_retry_actions/geneval2_balanced_100x5_round0_gpt55/retry_action_manifest.jsonl` | yes | 500 |
| raw trajectories | `data/raw_trajectories/geneval2_balanced_100x5_round0_gpt55` | yes | 500 |
| SFT output | `data/sft/geneval2_balanced_100x5_round0_retry_replan_sft.jsonl` | yes | - |

可用 identifier：`prompt_id`、`candidate_id`、`candidate_index`、`image_id`、`source_index`、`seed`、`image_path`。candidate-level mapping 已由 package manifest、diagnostic jobs 和 eval image map 共同提供。当前选择模式：`all_candidates`。

## 2. Summary Statistics

| metric | value |
|---|---:|
| number of prompts | 100 |
| number of initial images in manifest | 500 |
| selected initial images | 500 |
| pass rate before retry | 5.80% |
| failed samples with valid teacher retry plans | 471 |
| initial_success | 29 |
| retry_ready | 471 |

### Failure Type Distribution

| failure_type | count |
|---|---:|
| `attribute_mismatch` | 211 |
| `color_mismatch` | 102 |
| `count_mismatch` | 394 |
| `missing_object` | 78 |
| `relation_mismatch` | 144 |
| `spatial_mismatch` | 125 |

### Coverage

| coverage | count |
|---|---:|
| `attribute` | 500 |
| `count` | 500 |
| `multi_constraint` | 500 |
| `object` | 500 |
| `relation` | 500 |

## 3. 本阶段工作方式

1. 从 initial-plan generation manifest 选择目标 candidate 图片；本次可用 `--all-candidates` 覆盖每个 prompt 的 5 张图。
2. 运行或加载 GenEval2，归一化为包含 score、passed/failed/uncertain constraints 和 critical failure types 的 report。
3. 为每个 candidate 写 round-0 raw trajectory；round-0 memory 使用 `persistent_failures = failed_constraints`、`new_failures = []`、`score_delta_from_previous = null`。
4. 通过 stop rule 将通过样本标记为 `initial_success`。
5. 对失败样本调用 teacher 一次，输入 original prompt、metadata、initial plan、generation metadata、normalized diagnostic、compact memory、best-so-far 和 previous action。
6. teacher 返回 strict JSON `retry_replan` 后，将样本标记为 `retry_ready`。
7. 默认不生成 retry 图片；本阶段只准备下一轮 retry generation 所需状态和 SFT 目标。

## 4. Patched Files / Functions

- `src/gen_retry/offline_planner.py`: round-0 memory、`retry_ready_action`、status、teacher request state。
- `src/gen_retry/evaluators/geneval2_result_normalizer.py`: GenEval2 score-list/atom-row normalization。
- `src/gen_retry/offline_package_builder.py`: manifest + initial plan + eval report package construction。
- `src/gen_retry/retry_plan_batch.py`: package rebuild、preflight、teacher call、quality report batch orchestration。
- `src/gen_retry/export/export_offline_sft.py`: candidate-level trajectory to step-level retry SFT export。
- `src/gen_retry/geneval2_retry_report.py`: 本报告和 summary stats 生成。
- `scripts/run_geneval2_batch.py`: GenEval2 batch runner；temporary work dir stays under output dir。
- `scripts/prepare_geneval2_retry_inputs.py`: no-API prepare checkpoint。
- `scripts/build_geneval2_retry_plans.py`: one-shot teacher retry planning batch。
- `scripts/export_offline_retry_sft.py`: SFT export CLI。
- `scripts/report_geneval2_retry_stage.py`: 本报告 CLI。

## 5. Runnable Command Example

```bash
python3 scripts/run_geneval2_batch.py \
  --manifest data/qwen_geneval2_balanced_100_x5_initial_gpt55_a100/generation_manifest.jsonl \
  --output-dir data/geneval2_jobs/balanced100_all_candidates \
  --geneval2-root ../GenEval2 \
  --qwen3vl-model-path /root/private_data/agentic_image/models/Qwen3-VL-8B-Instruct \
  --all-candidates \
  --limit 500 \
  --n-samples 5 \
  --method soft_tifa_gm \
  --atom-threshold 0.9 \
  --keep-eval-inputs \
  --resume
```

```bash
python3 scripts/prepare_geneval2_retry_inputs.py \
  --manifest data/qwen_geneval2_balanced_100_x5_initial_gpt55_a100/generation_manifest.jsonl \
  --package-dir data/incoming_generation_results/geneval2_balanced_100x5_round0_with_eval \
  --initial-plan-dir data/plans/initial/geneval2_balanced_100_gpt55 \
  --diagnostic-jobs data/geneval2_jobs/balanced100_all_candidates/diagnostic_jobs.jsonl \
  --eval-results data/geneval2_jobs/balanced100_all_candidates/normalized_reports.jsonl \
  --all-candidates \
  --limit 500
```

```bash
python3 scripts/build_geneval2_retry_plans.py \
  --package-dir data/incoming_generation_results/geneval2_balanced_100x5_round0_with_eval \
  --output-dir data/outgoing_retry_actions/geneval2_balanced_100x5_round0_gpt55 \
  --trajectory-dir data/raw_trajectories/geneval2_balanced_100x5_round0_gpt55 \
  --eval-results data/geneval2_jobs/balanced100_all_candidates/normalized_reports.jsonl \
  --diagnostic-jobs data/geneval2_jobs/balanced100_all_candidates/diagnostic_jobs.jsonl \
  --limit 500 \
  --teacher gpt55 \
  --max-retry 3
```

```bash
python3 scripts/export_offline_retry_sft.py \
  --trajectories-dir data/raw_trajectories/geneval2_balanced_100x5_round0_gpt55 \
  --output data/sft/geneval2_balanced_100x5_round0_retry_replan_sft.jsonl \
  --rejected-output data/rejected/geneval2_balanced_100x5_round0_retry_replan_rejected.jsonl
```

```bash
python3 scripts/report_geneval2_retry_stage.py \
  --package-manifest data/incoming_generation_results/geneval2_balanced_100x5_round0_with_eval/package_manifest.jsonl \
  --diagnostic-jobs data/geneval2_jobs/balanced100_all_candidates/diagnostic_jobs.jsonl \
  --eval-results data/geneval2_jobs/balanced100_all_candidates/normalized_reports.jsonl \
  --retry-manifest data/outgoing_retry_actions/geneval2_balanced_100x5_round0_gpt55/retry_action_manifest.jsonl \
  --trajectory-dir data/raw_trajectories/geneval2_balanced_100x5_round0_gpt55 \
  --sft-output data/sft/geneval2_balanced_100x5_round0_retry_replan_sft.jsonl \
  --all-candidates \
  --limit 500 \
  --markdown-output docs/GENEVAL2_BALANCED100_RETRY_TRAJECTORY_REPORT.md \
  --summary-output data/analysis/geneval2_balanced100_retry_stage_summary.json
```

## 6. Blockers

- 当前报告未发现数据层 blocker。

## 7. Teacher API Provenance Note

- 主体 teacher retry pass 使用 OpenAI-compatible relay 的 `gpt-5.5`。
- 最后一批中 `gpt-5.5` 对 32 个 candidate 持续返回 HTTP 503；同一时间 `/models` 可用，但极小 chat/completions 请求也对 `gpt-5.5` 返回 503。
- 为避免留下 32 条 `error` trajectory，这 32 个 candidate 使用同一 relay 的 `gpt-5.4` fallback 重新调用 teacher，并成功覆盖为 `retry_ready`。
- 因此最终 471 条 retry SFT 里有 32 条 teacher action 来自 `gpt-5.4` fallback；如果训练需要严格单一 teacher model provenance，应在过滤阶段按 API log 或 candidate list 单独标记/处理。
