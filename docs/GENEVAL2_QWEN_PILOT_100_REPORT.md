# GenEval2 Qwen-Image 100 Prompt Pilot

更新日期：2026-07-02

## 目标复核

当前优先级是先让生图跑起来，避免后续 teacher API / retry pipeline 工作阻塞 GPU：

- 从 GenEval2 抽取 100 条 prompt。
- 每条 prompt 生成 5 张 Qwen-Image-2512 初始候选，共 500 张。
- 生成过程必须有总进度、ETA、日志和可恢复能力。
- 先完成初始生成；teacher initial plan、GenEval2 evaluation、retry replan、SFT export 后续接上。

这不是训练任务，也不是完整 RL 实现。

## 已存在能力

- `scripts/generate_qwen_geneval_images.py`：可以调用本地 Qwen-Image pipeline，按 GenEval image layout 写图片和 manifest。
- `scripts/collect_qwen_geneval_diagnostics.py`：可以用 command template 跑生成和 Geneval，并写 candidate diagnostics。
- `src/gen_retry/teachers/gpt55_teacher_adapter.py`：已有 OpenAI-compatible teacher API adapter。
- `src/gen_retry/prompts/initial_plan_prompt.py` 和 `retry_replan_prompt.py`：已有结构化 initial/retry action prompt。
- `src/gen_retry/collectors/collect_episodes.py`：已有同步 episode collector 和 retry memory 字段。

## 本次补齐

- 新增 `scripts/select_balanced_geneval2_prompts.py`，从 `../GenEval2/geneval2_data.jsonl` 选择 100 条 retry pilot prompt。
- 新增 `src/gen_retry/utils/progress.py`，提供总量进度、elapsed、ETA、rate。
- `scripts/generate_qwen_geneval_images.py`：
  - 单 shard 按图片级输出进度；
  - 多 GPU/多 shard 父进程按已生成图片文件数输出 `0/500` 这类总进度；
  - manifest 的 `candidate_id` 改为基于 `prompt_id`；
  - 增加 `--progress-interval`。
- `scripts/collect_qwen_geneval_diagnostics.py` 和 `src/gen_retry/collectors/qwen_geneval_batch.py`：
  - command-template 生成/评估阶段也有总进度和 ETA；
  - candidate id 优先使用输入 prompt 的 `prompt_id`。
- 新增 `scripts/precompute_initial_plans.py`：
  - 支持 `--teacher gpt55|mock`；
  - 每个 prompt 一个 deterministic JSON cache；
  - 支持 `--resume`、多 worker、错误目录和总进度/ETA。
- 新增 `scripts/run_geneval2_batch.py`：
  - 支持 Qwen official image layout 或 generation manifest；
  - 为同一 prompt 的多张候选图生成唯一 candidate evaluation key，避免官方 GenEval2 的 prompt-key 冲突；
  - 输出 raw score lists、atom rows、normalized reports；
  - 支持 `--plan-only` 和 `--allow-partial`，可在生成尚未完成时先验证下一阶段计划。
- 新增 `scripts/validate_geneval2_pilot_state.py`：
  - 检查 prompt JSONL 必填字段；
  - 检查 100 x 5 图片布局，可以 partial 或 strict；
  - 检查 manifest candidate id；
  - 检查 initial plan cache schema；
  - 检查 GenEval2 normalized report schema；
  - 解析生成日志中的 shard/total 进度与 ETA。

## 已生成文件

- Prompt 集：`data/prompts/geneval2_balanced_100.jsonl`
- Prompt 分布摘要：
  - `data/prompts/geneval2_balanced_100.summary.json`
  - `data/prompts/geneval2_balanced_100.summary.md`
- 500 候选 manifest：
  - `data/qwen_geneval2_balanced_100_x5_manifest/generation_manifest.jsonl`
- Qwen smoke 输出：
  - `data/qwen_geneval2_balanced_100_x5_smoke/`
- 完整生成输出目录：
  - `data/qwen_geneval2_balanced_100_x5_images/`
- 完整生成日志/PID：
  - `data/run_logs/qwen_geneval2_balanced_100_x5.log`
  - `data/run_logs/qwen_geneval2_balanced_100_x5.pid`
- Mock initial plan dry-run：
  - `data/plans/initial_mock_balanced_100/`
- GenEval2 batch plan-only smoke：
  - `data/geneval2/qwen_geneval2_balanced_100_x5_plan/`
- Pilot state validation summary：
  - `data/analysis/geneval2_qwen_pilot_state_partial.json`

## 已启动的完整生成任务

当前完整任务已经用 `setsid` 启动：

```bash
cat data/run_logs/qwen_geneval2_balanced_100_x5.pid
```

记录时父进程 PID 为 `1036`，子进程 PID 为 `1042`。输出目录中已生成至少 `13/500` 张；shard 级 ETA 约 `10:35:29`。父进程总 ETA 在前几张时包含模型加载时间，初期会偏大，完成更多图片后会稳定。

监控命令：

```bash
tail -f data/run_logs/qwen_geneval2_balanced_100_x5.log
find data/qwen_geneval2_balanced_100_x5_images -path '*/samples/*.png' -type f | wc -l
ps -p "$(cat data/run_logs/qwen_geneval2_balanced_100_x5.pid)" -o pid=,ppid=,stat=,etime=,cmd=
nvidia-smi
```

如进程中断，直接重跑同一命令即可；`--resume` 会跳过已存在图片：

```bash
python3 scripts/generate_qwen_geneval_images.py \
  --metadata data/prompts/geneval2_balanced_100.jsonl \
  --output-dir data/qwen_geneval2_balanced_100_x5_images \
  --model-path ../models/Qwen-Image-2512 \
  --n-samples 5 \
  --limit 100 \
  --seed 1000 \
  --gpus 0 \
  --workers-per-gpu 1 \
  --dtype bfloat16 \
  --width 1664 \
  --height 928 \
  --steps 50 \
  --true-cfg-scale 4.0 \
  --negative-prompt ' ' \
  --positive-suffix ', Ultra HD, 4K, cinematic composition.' \
  --resume \
  --skip-grid \
  --progress-interval 60
```

## 本次验证

```bash
python3 scripts/select_balanced_geneval2_prompts.py \
  --input ../GenEval2/geneval2_data.jsonl \
  --output data/prompts/geneval2_balanced_100.jsonl \
  --num-prompts 100

python3 scripts/collect_qwen_geneval_diagnostics.py \
  --prompts data/prompts/geneval2_balanced_100.jsonl \
  --output-dir data/qwen_geneval2_balanced_100_x5_manifest \
  --images-per-prompt 5 \
  --gpus 0 \
  --qwen-model-path ../models/Qwen-Image-2512 \
  --plan-only \
  --limit 100

python3 -m compileall src scripts tests
git diff --check -- scripts/select_balanced_geneval2_prompts.py scripts/precompute_initial_plans.py scripts/run_geneval2_batch.py scripts/generate_qwen_geneval_images.py scripts/collect_qwen_geneval_diagnostics.py src/gen_retry/collectors/qwen_geneval_batch.py src/gen_retry/utils/progress.py
```

Validation result:

- Prompt JSONL：100 rows。
- Candidate manifest：500 rows。
- compileall：passed。
- diff whitespace check：passed。
- Real Qwen smoke：1 image generated successfully.
- Mock initial plan dry-run：100/100 passed，不调用真实 API。
- GenEval2 batch plan-only smoke：当前生成中状态下规划到 7 个已有 image job、493 个 missing image，不启动评估模型。
- Pilot state validation：当前生成中状态下 `13/500` image layout existing、487 missing；prompt/manifest/mock initial-plan cache 均无结构错误。

## 后续可运行命令

Teacher initial plan cache（真实 API 环境中运行；需要 `GEN_RETRY_TEACHER_*`）：

```bash
python3 scripts/precompute_initial_plans.py \
  --prompts data/prompts/geneval2_balanced_100.jsonl \
  --output-dir data/plans/initial/geneval2_balanced_100_gpt55 \
  --teacher gpt55 \
  --num-workers 4 \
  --resume
```

本地无 API smoke：

```bash
python3 scripts/precompute_initial_plans.py \
  --prompts data/prompts/geneval2_balanced_100.jsonl \
  --output-dir data/plans/initial_mock_balanced_100 \
  --teacher mock \
  --num-workers 4 \
  --resume
```

500 张图完成后运行 GenEval2 batch evaluation：

```bash
python3 scripts/run_geneval2_batch.py \
  --metadata data/prompts/geneval2_balanced_100.jsonl \
  --image-dir data/qwen_geneval2_balanced_100_x5_images \
  --output-dir data/geneval2/qwen_geneval2_balanced_100_x5 \
  --geneval2-root ../GenEval2 \
  --qwen3vl-model-path ../models/Qwen3-VL-8B-Instruct \
  --n-samples 5 \
  --limit 100 \
  --method soft_tifa_gm \
  --atom-threshold 0.9 \
  --resume
```

随时检查当前 pilot 状态：

```bash
python3 scripts/validate_geneval2_pilot_state.py \
  --prompts data/prompts/geneval2_balanced_100.jsonl \
  --image-dir data/qwen_geneval2_balanced_100_x5_images \
  --manifest data/qwen_geneval2_balanced_100_x5_manifest/generation_manifest.jsonl \
  --plan-dir data/plans/initial_mock_balanced_100 \
  --run-log data/run_logs/qwen_geneval2_balanced_100_x5.log \
  --expected-prompts 100 \
  --images-per-prompt 5 \
  --allow-partial-images \
  --output data/analysis/geneval2_qwen_pilot_state_partial.json
```

## 下一步

1. 等待 500 张初始图片完成。
2. 合并/检查 `generation_manifest.jsonl`，确认图片路径全存在。
3. 接 GenEval2 evaluation，生成 normalized reports。
4. 对失败候选批量调用 teacher `retry_replan`。
5. 进入 retry generation/evaluation，直到 `max_retry=3`。
