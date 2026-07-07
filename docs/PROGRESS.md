# Progress
## Geneval2 Balanced-100 Retry Trajectory Contract Patch

Status: local trajectory/SFT contract patched and validated; still pending real GenEval2 diagnostics and GPT teacher retry API execution for the 100 candidate-0 images.

Completed work:

- Re-read the active request from `/root/.codex/attachments/12c51780-6103-4d9e-8a5d-ab9c1460edc7/pasted-text-1.txt`.
- Audited the current 100-batch data state:
  - 100 prompt rows in `data/prompts/geneval2_balanced_100.jsonl`.
  - 500 manifest rows and 500 existing local initial-plan images in `data/qwen_geneval2_balanced_100_x5_initial_gpt55_a100/`.
  - 100 candidate-0 rows/images selected for this stage.
  - 100 valid initial plan cache files in `data/plans/initial/geneval2_balanced_100_gpt55/`.
  - 100 candidate-0 generation packages in `data/incoming_generation_results/geneval2_balanced_100_round0_initial_gpt55/`.
  - 100 candidate-0 GenEval2 diagnostic jobs in `data/geneval2_jobs/balanced100_candidate0/`.
  - 0 attached normalized GenEval2 reports and 0 current 100-batch teacher retry plans.
- Patched `src/gen_retry/offline_planner.py` so candidate-level raw trajectories match the round-0 contract:
  - round-0 `attempts[].planner_action` remains the `initial_plan` that produced the image.
  - the teacher's next action is saved as top-level `retry_ready_action` / `latest_teacher_action`.
  - round-0 memory uses `persistent_failures = failed_constraints`, `new_failures = []`, `score_delta_from_previous = null`, and `score_delta_from_best = 0.0`.
  - memory now records `current_round` and `previous_action`.
  - failed round-0 teacher state records `retry_round = 1`.
  - retry action packages now include `status` and `retry_ready_action`.
- Patched the retry prompt/GPT adapter path to allow `score_delta_from_previous = null` for round 0.
- Added offline candidate-level SFT export:
  - `src/gen_retry/export/export_offline_sft.py`
  - `scripts/export_offline_retry_sft.py`
  - default export removes local image artifact paths, raw eval paths/reports, and raw image upload fields from SFT input.
- Added tests for the new trajectory contract and offline SFT exporter.
- Added the requested Chinese report at `docs/GENEVAL2_BALANCED100_RETRY_TRAJECTORY_REPORT.md`.
- Updated offline pipeline and SFT export docs with the stricter round-0 trajectory shape and new export command.

Changed files:

- `src/gen_retry/offline_planner.py`
- `src/gen_retry/prompts/retry_replan_prompt.py`
- `src/gen_retry/teachers/gpt55_teacher_adapter.py`
- `src/gen_retry/export/__init__.py`
- `src/gen_retry/export/export_offline_sft.py`
- `scripts/export_offline_retry_sft.py`
- `tests/test_offline_planner.py`
- `tests/test_export_offline_sft.py`
- `docs/OFFLINE_GENEVAL2_RETRY_PIPELINE.md`
- `docs/SFT_EXPORT_FORMATS.md`
- `docs/GENEVAL2_BALANCED100_RETRY_TRAJECTORY_REPORT.md`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- `python3 -m unittest tests.test_offline_planner tests.test_export_offline_sft tests.test_teacher_request_preview tests.test_retry_plan_batch` - passed with 5 tests.
- `python3 -m compileall src/gen_retry/offline_planner.py src/gen_retry/prompts/retry_replan_prompt.py src/gen_retry/teachers/gpt55_teacher_adapter.py src/gen_retry/export/export_offline_sft.py scripts/export_offline_retry_sft.py tests/test_export_offline_sft.py` - passed.
- `python3 -m unittest tests.test_gpt55_teacher_adapter tests.test_retry_plan_quality tests.test_export_offline_sft tests.test_offline_planner tests.test_retry_plan_batch tests.test_teacher_request_preview` - passed with 9 tests.
- `python3 -m compileall src scripts tests` - passed.
- `python3 -m unittest discover tests` - passed with 70 tests.
- `python3 scripts/safe_check.py` - passed.
- `python3 -m json.tool data/geneval2_jobs/balanced100_candidate0/geneval2_batch_plan.json` - passed.
- `python3 -m json.tool data/geneval2_jobs/balanced100_candidate0/eval_image_paths.json` - passed.
- `python3 scripts/export_offline_retry_sft.py --help` - passed.
- `python3 scripts/check_geneval2_retry_inputs.py --package-manifest data/incoming_generation_results/geneval2_balanced_100_round0_initial_gpt55/package_manifest.jsonl --diagnostic-jobs data/geneval2_jobs/balanced100_candidate0/diagnostic_jobs.jsonl --expected-count 100 --output data/geneval2_jobs/balanced100_candidate0/retry_input_preflight_no_eval.json` - passed with `package_count=100`, `diagnostic_job_count=100`, `critical_count=0`.
- `git diff --check` - passed.

Blockers:

- No real GenEval2 normalized diagnostics are present for the 100 candidate-0 images, so pass/fail rate and failure type distribution cannot be computed yet.
- No GPT teacher retry API calls were made because the eval reports are missing.
- No current 100-batch raw trajectories or SFT rows exist yet; the code path is ready to produce them once diagnostics and teacher plans are available.

Next recommended step:

- Run or attach GenEval2 diagnostics for `data/geneval2_jobs/balanced100_candidate0/`, then run `scripts/prepare_geneval2_retry_inputs.py`, preview teacher requests, run `scripts/build_geneval2_retry_plans.py --teacher gpt55`, and finally export step-level SFT with `scripts/export_offline_retry_sft.py`.

## Geneval2 Balanced-100 First-Pass Retry Packages

Status: completed for ingest/package construction; pending real GenEval2 diagnostics and GPT teacher retry API execution.

Completed work:

- Added `src/gen_retry/offline_package_builder.py` to build offline generation packages from Qwen generation manifests.
- Added `scripts/build_geneval2_retry_packages.py` CLI.
- Built 100 round-0 generation packages from `data/qwen_geneval2_balanced_100_x5_initial_gpt55_a100/generation_manifest.jsonl`, using `candidate_index=0` and pairing every row with `data/plans/initial/geneval2_balanced_100_gpt55/`.
- Wrote package outputs to `data/incoming_generation_results/geneval2_balanced_100_round0_initial_gpt55/`.
- Updated `src/gen_retry/offline_planner.py` so local image bytes are only required when Machine B must run GenEval2 itself. If normalized evaluation is embedded or supplied, teacher retry planning can proceed from JSON diagnostics and history context.
- Persisted `teacher_request` in retry action packages and raw trajectories for audit/SFT construction.
- Strengthened the retry replan prompt with explicit quality rules for count, attribute/color, spatial/relation, persistent failures, and preservation of passed constraints.
- Added `--allow-missing-images` to `scripts/validate_offline_retry_package.py`.
- Updated `docs/OFFLINE_GENEVAL2_RETRY_PIPELINE.md` with the 100-package command flow and the image-handling boundary.
- Extended `scripts/run_geneval2_batch.py` with `--candidate-index` manifest filtering and plan-only diagnostic input writing.
- Generated 100 candidate-0 GenEval2 diagnostic jobs in `data/geneval2_jobs/balanced100_candidate0/` without running the verifier.
- Added `src/gen_retry/retry_plan_batch.py` and `scripts/build_geneval2_retry_plans.py` to rebuild packages from returned diagnostics and run teacher retry planning in one resumable batch.
- Added retry plan quality checks in `src/gen_retry/quality/retry_plan_quality.py` and `scripts/check_retry_plan_quality.py`.
- `run_retry_plan_batch()` now writes `retry_plan_quality_report.json` and marks the batch summary `error` when any critical quality issue is found.
- Added GenEval2 retry input preflight checks in `src/gen_retry/quality/geneval2_retry_inputs.py` and `scripts/check_geneval2_retry_inputs.py`.
- `run_retry_plan_batch()` now writes `retry_input_preflight.json` and stops before teacher API calls if the returned diagnostics are incomplete, duplicated, invalid, or not aligned with the package manifest.
- Verified the current 100 package manifest and candidate-0 diagnostic job plan align cleanly before eval results are attached.
- Fixed official GenEval2 `raw_score_lists.json` normalization so `eval_benchmark.jsonl` candidate identity is preserved into atom rows and `normalized_reports.jsonl`.
- `scripts/normalize_geneval2_results.py` now writes explicit `candidate_id`, `prompt_id`, `source_index`, and `candidate_index` fields for candidate-level retry pairing.
- Added `src/gen_retry/geneval2_retry_prepare.py` and `scripts/prepare_geneval2_retry_inputs.py` as a no-API checkpoint for returned diagnostics: normalize raw score lists if needed, rebuild with-eval packages, run preflight, and write `prepare_summary.json`.
- Added `src/gen_retry/teacher_request_preview.py` and `scripts/preview_geneval2_teacher_requests.py` to export the exact teacher retry JSON context before API calls and verify it does not contain raw image upload keys.
- Added semantic retry-action quality checks in `src/gen_retry/quality/retry_action_quality.py`; `GPT55TeacherAdapter.retry_replan()` now asks the teacher to repair schema-valid but diagnostic-incomplete responses before accepting them.

Changed files:

- `src/gen_retry/offline_package_builder.py`
- `scripts/build_geneval2_retry_packages.py`
- `scripts/build_geneval2_retry_plans.py`
- `scripts/check_retry_plan_quality.py`
- `scripts/check_geneval2_retry_inputs.py`
- `scripts/normalize_geneval2_results.py`
- `scripts/prepare_geneval2_retry_inputs.py`
- `scripts/preview_geneval2_teacher_requests.py`
- `src/gen_retry/geneval2_retry_prepare.py`
- `src/gen_retry/teacher_request_preview.py`
- `src/gen_retry/offline_planner.py`
- `src/gen_retry/evaluators/geneval2_result_normalizer.py`
- `src/gen_retry/quality/__init__.py`
- `src/gen_retry/quality/geneval2_retry_inputs.py`
- `src/gen_retry/quality/retry_plan_quality.py`
- `src/gen_retry/quality/retry_action_quality.py`
- `src/gen_retry/retry_plan_batch.py`
- `src/gen_retry/teachers/gpt55_teacher_adapter.py`
- `src/gen_retry/prompts/retry_replan_prompt.py`
- `scripts/validate_offline_retry_package.py`
- `tests/test_offline_package_builder.py`
- `tests/test_retry_plan_batch.py`
- `tests/test_geneval2_retry_inputs.py`
- `tests/test_geneval2_result_normalizer.py`
- `tests/test_normalize_geneval2_results_script.py`
- `tests/test_geneval2_retry_prepare.py`
- `tests/test_teacher_request_preview.py`
- `tests/test_gpt55_teacher_adapter.py`
- `tests/test_retry_plan_quality.py`
- `tests/test_run_geneval2_batch.py`
- `docs/OFFLINE_GENEVAL2_RETRY_PIPELINE.md`
- `docs/QWEN_GENEVAL_BATCH.md`
- `data/incoming_generation_results/geneval2_balanced_100_round0_initial_gpt55/*.json`
- `data/incoming_generation_results/geneval2_balanced_100_round0_initial_gpt55/package_manifest.jsonl`
- `data/geneval2_jobs/balanced100_candidate0/diagnostic_jobs.jsonl`
- `data/geneval2_jobs/balanced100_candidate0/eval_benchmark.jsonl`
- `data/geneval2_jobs/balanced100_candidate0/eval_image_paths.json`
- `data/geneval2_jobs/balanced100_candidate0/geneval2_batch_plan.json`
- `data/geneval2_jobs/balanced100_candidate0/retry_input_preflight_no_eval.json`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- `python3 scripts/build_geneval2_retry_packages.py --manifest data/qwen_geneval2_balanced_100_x5_initial_gpt55_a100/generation_manifest.jsonl --output-dir data/incoming_generation_results/geneval2_balanced_100_round0_initial_gpt55 --initial-plan-dir data/plans/initial/geneval2_balanced_100_gpt55 --candidate-index 0 --limit 100 --require-initial-plan` - passed with `package_count=100`, `missing_initial_plan_count=0`.
- `python3 scripts/validate_offline_retry_package.py data/incoming_generation_results/geneval2_balanced_100_round0_initial_gpt55/*.json` - passed for all 100 packages.
- `python3 scripts/run_geneval2_batch.py --manifest data/qwen_geneval2_balanced_100_x5_initial_gpt55_a100/generation_manifest.jsonl --output-dir data/geneval2_jobs/balanced100_candidate0 --candidate-index 0 --limit 100 --n-samples 5 --plan-only --keep-eval-inputs` - passed with `planned GenEval2 jobs=100 missing=0`.
- `python3 -m json.tool data/geneval2_jobs/balanced100_candidate0/geneval2_batch_plan.json` - passed.
- `python3 -m json.tool data/geneval2_jobs/balanced100_candidate0/eval_image_paths.json` - passed.
- `python3 scripts/build_geneval2_retry_plans.py --help` - passed.
- `python3 scripts/check_retry_plan_quality.py --help` - passed.
- `python3 scripts/check_geneval2_retry_inputs.py --help >/dev/null` - passed.
- `python3 scripts/normalize_geneval2_results.py --help >/dev/null` - passed.
- `python3 scripts/prepare_geneval2_retry_inputs.py --help >/dev/null` - passed.
- `python3 scripts/preview_geneval2_teacher_requests.py --help >/dev/null` - passed.
- `python3 scripts/check_geneval2_retry_inputs.py --package-manifest data/incoming_generation_results/geneval2_balanced_100_round0_initial_gpt55/package_manifest.jsonl --diagnostic-jobs data/geneval2_jobs/balanced100_candidate0/diagnostic_jobs.jsonl --expected-count 100 --output data/geneval2_jobs/balanced100_candidate0/retry_input_preflight_no_eval.json` - passed with `package_count=100`, `diagnostic_job_count=100`, `critical_count=0`.
- `python3 -m compileall src scripts tests` - passed.
- `python3 -m unittest tests.test_geneval2_retry_prepare` - passed with 2 tests.
- `python3 -m unittest tests.test_teacher_request_preview` - passed with 2 tests.
- `python3 -m unittest tests.test_gpt55_teacher_adapter tests.test_retry_plan_quality` - passed with 4 tests.
- `python3 -m unittest tests.test_geneval2_retry_inputs tests.test_retry_plan_batch` - passed with 3 tests.
- `python3 -m unittest tests.test_geneval2_result_normalizer tests.test_normalize_geneval2_results_script tests.test_retry_plan_batch` - passed with 13 tests.
- `python3 -m unittest discover tests` - passed with 69 tests.
- `python3 scripts/safe_check.py` - passed.

Blockers:

- No real GenEval2 normalized diagnostic file has been attached to these 100 packages yet.
- No GPT teacher retry API calls were made in this checkpoint.

Next recommended step:

- Run GenEval2 diagnostics for the 100 selected first-pass images, save normalized results keyed by `candidate_id`, run `scripts/check_geneval2_retry_inputs.py` with `--eval-results`, then run `scripts/build_geneval2_retry_plans.py --teacher gpt55` to rebuild packages and produce retry plans. Teacher retry planning does not require uploading raw images; it needs the normalized diagnostic and trajectory context.

## Remaining GenEval2 Initial Plans

Status: completed.

Completed work:

- Clarified the remaining prompt scope as unique GenEval2 prompts not already present in `data/prompts/geneval2_balanced_100.jsonl`.
- Counted 148 rows across the other `geneval2_*.jsonl` files, with 45 rows overlapping balanced 100 and 40 duplicate rows among the remaining files.
- Built canonical remaining prompt set: `data/prompts/geneval2_remaining_after_balanced100.jsonl` with 63 unique non-overlapping prompts.
- Built canonical plan cache: `data/plans/initial/geneval2_remaining_after_balanced100_gpt55/` with 63 valid GPT teacher `initial_plan` files.
- Stopped the earlier broad per-file precompute after realizing some prompt files overlap balanced 100. The completed non-overlapping API batches already covered all 63 canonical remaining prompts. The partial `geneval2_static_position_20_gpt55` cache is not part of the canonical remaining set.
- Fixed `scripts/generate_qwen_geneval_images.py` fallback prompt-id logic so files without `prompt_id` match `scripts/precompute_initial_plans.py`.

Changed files:

- `scripts/generate_qwen_geneval_images.py`
- `data/prompts/geneval2_remaining_after_balanced100.jsonl`
- `data/plans/initial/geneval2_remaining_after_balanced100_gpt55/*.json`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`
- `docs/QWEN_GENEVAL_BATCH.md`

Validation commands run:

- `python3 -m compileall scripts/generate_qwen_geneval_images.py scripts/generate_qwen_geneval_images_dcu.py scripts/precompute_initial_plans.py` - passed.
- `python3 scripts/precompute_initial_plans.py --prompts data/prompts/geneval2_remaining_after_balanced100.jsonl --output-dir data/plans/initial/geneval2_remaining_after_balanced100_gpt55 --teacher gpt55 --evaluator-type geneval2 --num-workers 4 --resume --progress-interval 30` - passed with `loaded=63 skipped_valid=63 pending=0`.
- Custom stdlib cache audit - passed with 63 rows, 63 plan files, 0 missing, 0 invalid, 0 overlap with balanced 100.
- Custom generation attach check - passed with 63 attached plan-conditioned prompts and 0 empty generation prompts.

Blockers:

- None for initial-plan cache coverage.
- Real Qwen-Image generation was not run locally.

Next recommended step:

- Use fresh A100 output directories and pass `--initial-plan-dir` for both the balanced 100 set and the canonical remaining 63 set.

## Plan-Conditioned Initial Generation Ready

Status: completed.

Completed work:

- Verified `data/prompts/geneval2_balanced_100.jsonl` has 100 prompt rows and `data/plans/initial/geneval2_balanced_100_gpt55/` has 100 valid cached GPT teacher `initial_plan` files with non-empty `initial_prompt`.
- Ran the initial-plan precompute entry point with `--resume`; it reported `loaded=100 skipped_valid=100 pending=0`, so no new API calls were needed.
- Added `--initial-plan-dir` to `scripts/generate_qwen_geneval_images.py`; generation now uses `initial_plan.initial_prompt` while preserving original Geneval2 prompt metadata.
- Added manifest fields for `original_prompt`, `generation_prompt`, and `generation_prompt_source`.
- Added a resume guard so an existing raw-prompt output directory is not silently reused as plan-conditioned output.
- Updated the DCU command to use a fresh plan-conditioned output directory.

Changed files:

- `scripts/generate_qwen_geneval_images.py`
- `docs/QWEN_GENEVAL_BATCH.md`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- `python3 scripts/precompute_initial_plans.py --prompts data/prompts/geneval2_balanced_100.jsonl --output-dir data/plans/initial/geneval2_balanced_100_gpt55 --teacher gpt55 --evaluator-type geneval2 --num-workers 4 --resume --progress-interval 30` - passed with `pending=0`.
- Custom stdlib cache check - passed with 100 prompt rows and 100 valid initial plans with non-empty `initial_prompt`.
- `python3 -m compileall scripts/generate_qwen_geneval_images.py scripts/generate_qwen_geneval_images_dcu.py` - passed.
- `python3 scripts/generate_qwen_geneval_images.py --help` - passed and shows `--initial-plan-dir`.
- `python3 scripts/generate_qwen_geneval_images_dcu.py --help` - passed and shows `--initial-plan-dir`.
- Custom stdlib attach check - passed with 100 plan-conditioned rows and 0 empty generation prompts.
- Resume guard smoke against the old raw-prompt output dir - failed as expected before model loading with a different generation prompt error.
- Fresh-output metadata preflight check - passed.

Blockers:

- No real Qwen-Image generation was run locally.
- No new teacher API calls were made in this turn because all 100 cached plans were already valid and local `GEN_RETRY_TEACHER_*` variables were not set.

Next recommended step:

- Run `scripts/generate_qwen_geneval_images_dcu.py` on the generation server with `--initial-plan-dir data/plans/initial/geneval2_balanced_100_gpt55` and a fresh output dir such as `data/qwen_geneval2_balanced_100_x5_initial_gpt55_images`.

## DCU Qwen Generation Entry Point

Status: completed.

Completed work:

- Added configurable worker visibility environment support to `scripts/generate_qwen_geneval_images.py`.
- Added `scripts/generate_qwen_geneval_images_dcu.py`, a DCU/ROCm wrapper that defaults worker masking to `HIP_VISIBLE_DEVICES` and clears `CUDA_VISIBLE_DEVICES,ROCR_VISIBLE_DEVICES` in worker environments.
- Documented the four-card DCU command in `docs/QWEN_GENEVAL_BATCH.md`.

Changed files:

- `scripts/generate_qwen_geneval_images.py`
- `scripts/generate_qwen_geneval_images_dcu.py`
- `docs/QWEN_GENEVAL_BATCH.md`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- `python3 -m compileall scripts/generate_qwen_geneval_images.py scripts/generate_qwen_geneval_images_dcu.py` - passed.
- `python3 scripts/generate_qwen_geneval_images_dcu.py --help` - passed.
- `python3 scripts/generate_qwen_geneval_images.py --help` - passed.
- `HIP_VISIBLE_DEVICES=1,2,3,4 python3 -c ...resolve_gpu_ids...` - passed and resolved logical `0,1,2,3` to physical `1,2,3,4`.

Blockers:

- Real Qwen-Image generation was not run on this local machine.

Next recommended step:

- Run the documented DCU command on the prepared generation server with the correct local `--model-path` and `HIP_VISIBLE_DEVICES` mask.


## Stage 1: Repository Digests

Status: completed.

Completed work:

- Read `AGENTS.md` and `docs/requests/00_project_brief.md`.
- Read `docs/requests/01_stage1_stage2_repo_digest_and_skeleton.md`.
- Inspected `../GenEvolve` as read-only.
- Inspected `../Gen-Searcher` as read-only.
- Inspected `../GenEval` as read-only.
- Wrote persistent digests under `docs/repo_digests/`.
- Wrote `docs/CODEBASE_MAP.md`.

Changed files:

- `docs/repo_digests/genevolve_digest.md`
- `docs/repo_digests/gen_searcher_digest.md`
- `docs/repo_digests/geneval_digest.md`
- `docs/CODEBASE_MAP.md`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

## Stage 2: Skeleton

Status: completed.

Completed work:

- Added package skeleton under `src/gen_retry/`.
- Added stdlib diagnostic normalizer.
- Added stdlib trajectory validator.
- Added tool and skill registries.
- Added `configs/skills/geneval_skills.yaml`.
- Added teacher API placeholder config and `.env.example`.
- Added JSON schema and minimal examples.
- Added README with safe local validation commands.
- Added unittest-style test files for future controlled runs.

Changed files:

- `README.md`
- `pyproject.toml`
- `.env.example`
- `configs/skills/geneval_skills.yaml`
- `configs/teacher/teacher_api.example.yaml`
- `schemas/sft_trajectory.schema.json`
- `examples/geneval_diagnostic_example.json`
- `examples/geneval_retry_example.json`
- `src/gen_retry/**`
- `tests/test_diagnostic_normalizer.py`
- `tests/test_trajectory_schema.py`
- `.gitignore`

Validation commands run:

- `python3 scripts/safe_check.py` - passed.
- `python3 -m compileall src scripts tests` - passed.
- `python3 -m json.tool examples/geneval_diagnostic_example.json` - passed.
- `python3 -m json.tool examples/geneval_retry_example.json` - passed.

Blockers:

- None.

Next recommended step:

- Stage 3 should add a raw GenEval result adapter and a teacher trajectory builder, but only after the user explicitly requests it.

## Teacher API And SFT Builder

Status: completed.

Completed work:

- Added a stdlib OpenAI-compatible teacher client interface with environment-based configuration.
- Added Responses API first path with Chat Completions fallback.
- Added deterministic `--dry-run` mock teacher mode that does not require an API key.
- Added strict teacher retry-action schema and validator.
- Added teacher prompt template for Geneval diagnostics, normalized diagnostics, and skill library context.
- Added JSON/JSONL helper utilities.
- Added `scripts/build_teacher_retry_actions.py`.
- Added `scripts/build_sft_trajectories.py`.
- Added SFT data building docs.
- Added empty `data/raw`, `data/processed`, and `data/failed` placeholders.

Changed files:

- `src/gen_retry/data/io.py`
- `src/gen_retry/teacher/__init__.py`
- `src/gen_retry/teacher/client.py`
- `src/gen_retry/teacher/prompts.py`
- `src/gen_retry/teacher/schemas.py`
- `src/gen_retry/teacher/build_retry_action.py`
- `scripts/build_teacher_retry_actions.py`
- `scripts/build_sft_trajectories.py`
- `schemas/teacher_retry_action.schema.json`
- `tests/test_teacher_schema.py`
- `docs/SFT_DATA_BUILDING.md`
- `docs/CODEBASE_MAP.md`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`
- `data/raw/.gitkeep`
- `data/processed/.gitkeep`
- `data/failed/.gitkeep`

Validation commands run:

- `python3 scripts/safe_check.py` - passed.
- `python3 -m compileall src scripts tests` - passed.
- `python3 -m json.tool examples/geneval_diagnostic_example.json` - passed.
- `python3 -m json.tool examples/geneval_retry_example.json` - passed.

Blockers:

- None.

Next recommended step:

- Run the mock teacher/SFT generation commands documented in `docs/SFT_DATA_BUILDING.md` when output files are desired.

## Spatial Normalization And Full Episode SFT

Status: completed.

Completed work:

- Updated spatial diagnostic normalization so `checks.spatial_relation=false` produces structured `spatial_relation` failed constraints.
- Added spatial `repair_targets` routed to `spatial_layout` with placement instructions.
- Updated dry-run teacher repair formatting for structured spatial relation failures.
- Updated `scripts/build_sft_trajectories.py` to emit full mocked Geneval retry episodes by default.
- Kept compact SFT output available through `--trajectory-format compact` or `--compact`.
- Added `examples/geneval_retry_full_episode_example.json`.
- Generated `data/processed/geneval_retry_sft_5_full.jsonl` from the five smoke diagnostics and existing teacher actions.
- Updated SFT docs and schema step names for full episode trajectories.

Changed files:

- `src/gen_retry/eval/diagnostic_normalizer.py`
- `src/gen_retry/teacher/build_retry_action.py`
- `scripts/build_sft_trajectories.py`
- `schemas/sft_trajectory.schema.json`
- `examples/geneval_retry_full_episode_example.json`
- `data/processed/geneval_retry_sft_5_full.jsonl`
- `docs/SFT_DATA_BUILDING.md`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- `python3 scripts/safe_check.py` - passed.
- `python3 -m compileall src scripts tests` - passed.
- `python3 -m json.tool examples/geneval_diagnostic_example.json` - passed.
- `python3 -m json.tool examples/geneval_retry_example.json` - passed.

Blockers:

- None.

Next recommended step:

- Inspect the full smoke SFT rows before scaling to larger diagnostic batches.

## Five-Trajectory Quality Review

Status: completed.

Completed work:

- Reviewed all five full Geneval-Retry SFT smoke trajectories one by one.
- Created `docs/QUALITY_REVIEW_5.md` with per-trajectory verdicts and a scale/no-scale recommendation.
- Added `scripts/check_sft_quality.py`, a stdlib-only automatic SFT quality checker.
- Checked structure, tool/action coverage, failure typing, skill routing, preserve/repair fields, spatial normalization, and obvious secret leakage.
- Confirmed automatic critical checks pass, with warnings for detector metadata in trajectory context and stale spatial normalized fields in the source teacher-action file.

Changed files:

- `docs/QUALITY_REVIEW_5.md`
- `scripts/check_sft_quality.py`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- `python3 scripts/safe_check.py` - passed.
- `python3 -m compileall src scripts tests` - passed.
- `python3 scripts/check_sft_quality.py --sft data/processed/geneval_retry_sft_5_full.jsonl --diagnostics data/smoke/geneval_diagnostics_5.jsonl --actions data/processed/teacher_retry_actions_5.jsonl` - passed with 0 critical issues and 7 warnings.

Blockers:

- None.

Next recommended step:

- Sanitize or mask mock retry judge observations before scaling to 50 trajectories.

## Data Hygiene Before Scaling To 50

Status: completed.

Completed work:

- Updated the full SFT exporter to separate `assistant_trainable_messages`, `tool_observations`, `raw_detector_outputs`, and `non_trainable_context`.
- Added `masking_metadata` describing exactly which assistant targets to train and which context/tool/raw fields to mask.
- Added compact diagnostic export as the default SFT-facing format, with raw detail available through `--diagnostic-detail raw`.
- Changed the SFT builder to prefer the original diagnostics file over stale diagnostics embedded in teacher action rows.
- Regenerated `data/processed/geneval_retry_sft_5_full.jsonl`.
- Updated `scripts/check_sft_quality.py` to treat detector metadata in assistant train targets as critical, allow masked raw detector fields, and suppress stale source warnings when SFT normalization is authoritative.

Changed files:

- `scripts/build_sft_trajectories.py`
- `scripts/check_sft_quality.py`
- `data/processed/geneval_retry_sft_5_full.jsonl`
- `docs/SFT_DATA_BUILDING.md`
- `docs/QUALITY_REVIEW_5.md`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- `python3 scripts/safe_check.py` - passed.
- `python3 -m compileall src scripts tests` - passed.
- `python3 scripts/check_sft_quality.py --sft data/processed/geneval_retry_sft_5_full.jsonl --diagnostics data/smoke/geneval_diagnostics_5.jsonl --actions data/processed/teacher_retry_actions_5.jsonl` - passed with 0 critical issues and 0 warnings.

Blockers:

- None.

Next recommended step:

- Scale the smoke pipeline to 50 trajectories using the compact diagnostic default, then run `scripts/check_sft_quality.py` on the expanded file.

## Five-Sample SFT Exporters And Strategy Docs

Status: completed.

Completed work:

- Re-read `AGENTS.md` and stayed in safe unattended mode.
- Used only the existing five-sample smoke inputs:
  - `data/smoke/geneval_diagnostics_5.jsonl`
  - `data/processed/teacher_retry_actions_5.jsonl`
  - `data/processed/geneval_retry_sft_5_full.jsonl`
- Verified current five-sample SFT quality with 0 critical issues and 0 warnings.
- Added assistant-only SFT exporters for Qwen chat, ShareGPT/LLaMA-Factory, and TRL conversational formats.
- Added a stdlib-only export quality checker.
- Generated five-sample export examples:
  - `data/processed/export_qwen_5.jsonl`
  - `data/processed/export_sharegpt_5.jsonl`
  - `data/processed/export_trl_5.jsonl`
- Added exporter tests and a visibility/occlusion normalizer test.
- Added SFT export format documentation.
- Added SFT strategy and RL roadmap documentation.
- Added tomorrow request files for manual 50 API run, 500 scaling, SFT training planning, and RL design-only work.
- Kept RL as design-only; no RL code or config was created.
- Did not call network APIs, image generators, training, RL, or dependency installers.

Changed files:

- `src/gen_retry/data/exporters.py`
- `scripts/export_sft.py`
- `scripts/check_export_quality.py`
- `scripts/check_sft_quality.py`
- `src/gen_retry/eval/diagnostic_normalizer.py`
- `tests/test_exporters.py`
- `tests/test_diagnostic_normalizer.py`
- `data/processed/export_qwen_5.jsonl`
- `data/processed/export_sharegpt_5.jsonl`
- `data/processed/export_trl_5.jsonl`
- `docs/SFT_EXPORT_FORMATS.md`
- `docs/SFT_STRATEGY.md`
- `docs/RL_ROADMAP.md`
- `docs/requests/04_run_50_teacher_batch_manual.md`
- `docs/requests/05_scale_to_500.md`
- `docs/requests/06_sft_training_plan.md`
- `docs/requests/07_rl_design_only.md`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- `python3 scripts/safe_check.py` - passed.
- `python3 -m compileall src scripts tests` - passed.
- `python3 scripts/check_sft_quality.py --sft data/processed/geneval_retry_sft_5_full.jsonl --diagnostics data/smoke/geneval_diagnostics_5.jsonl --actions data/processed/teacher_retry_actions_5.jsonl` - passed with 0 critical issues and 0 warnings.
- `python3 scripts/check_export_quality.py data/processed/export_qwen_5.jsonl data/processed/export_sharegpt_5.jsonl data/processed/export_trl_5.jsonl` - passed with 0 critical issues and 0 warnings.
- `python3 -m unittest tests.test_diagnostic_normalizer tests.test_exporters tests.test_teacher_schema tests.test_trajectory_schema` - passed.

Blockers:

- Real teacher API calls should be run manually from a normal terminal. Codex sandboxed Python network access was not reliable during the earlier interrupted 50-sample attempt.

Next recommended step:

- From a normal terminal, run the manual 50-row teacher batch described in `docs/requests/04_run_50_teacher_batch_manual.md`, then build and check the 50-row full SFT and exports.

## Visual Retry Trajectory Collector Scaffold

Status: completed.

Completed work:

- Read the pasted collector specification from `/Users/z1x/.codex/attachments/883269ce-f7f4-4113-b76e-a6c47c680c43/pasted-text-1.txt`.
- Re-read `AGENTS.md` and kept all work inside the current `gen-retry` repository.
- Added stdlib dataclass schemas for constraints, normalized Geneval reports, teacher actions, attempts, and episodes.
- Added generator and retry executor interfaces.
- Added mock initial generator and mock retry executor that write placeholder local files only.
- Added Qwen-Image-Edit adapter skeleton with environment-variable wiring and no real API call.
- Added evaluator interface, Geneval report normalizer, and deterministic mock Geneval evaluator.
- Added teacher interface, mock teacher, teacher prompt builder, and GPT-5.5 teacher adapter skeleton.
- Added skill routing for count, color, spatial, missing object, extra object, and visibility failures.
- Added pass condition and transition classifier.
- Added episode validator.
- Added retry episode collector that runs prompt -> generation -> evaluation -> teacher action -> retry edit/regeneration -> re-evaluation until pass or budget.
- Added policy-only ShareGPT SFT exporter for state_t -> action_t rows.
- Added full episode JSONL exporter helper.
- Added mock collection, validation, and policy export CLI scripts.
- Added five sample prompt records under `data/prompts/sample_prompts.jsonl`.
- Ran mock collection and saved five valid raw episode JSON files under `data/raw_episodes/`.
- Saved mock placeholder image files under `data/images/`.
- Exported `data/sft/retry_policy_sft_sharegpt.jsonl` with five policy SFT rows.
- Updated README with mock commands and real adapter integration points.
- Added stdlib unit tests for schema, pass condition, mock teacher, mock collector, and policy SFT export.

Changed files:

- `README.md`
- `src/gen_retry/schemas/episode_schema.py`
- `src/gen_retry/generators/base.py`
- `src/gen_retry/generators/mock_initial_generator.py`
- `src/gen_retry/generators/qwen_image_edit_adapter.py`
- `src/gen_retry/evaluators/base.py`
- `src/gen_retry/evaluators/geneval_normalizer.py`
- `src/gen_retry/evaluators/mock_geneval_evaluator.py`
- `src/gen_retry/teachers/base.py`
- `src/gen_retry/teachers/mock_teacher.py`
- `src/gen_retry/teachers/gpt55_teacher_adapter.py`
- `src/gen_retry/teachers/teacher_prompt.py`
- `src/gen_retry/skills/skill_library.py`
- `src/gen_retry/collectors/retry_episode_collector.py`
- `src/gen_retry/export/export_policy_sft.py`
- `src/gen_retry/export/export_full_episode_sft.py`
- `src/gen_retry/filters/filter_episodes.py`
- `src/gen_retry/filters/validate_episode.py`
- `src/gen_retry/utils/io.py`
- `src/gen_retry/utils/ids.py`
- `src/gen_retry/utils/logging.py`
- `scripts/collect_mock_episodes.py`
- `scripts/export_policy_sft.py`
- `scripts/validate_episodes.py`
- `data/prompts/sample_prompts.jsonl`
- `data/raw_episodes/*.json`
- `data/images/*.png`
- `data/sft/retry_policy_sft_sharegpt.jsonl`
- `tests/test_retry_episode_schema.py`
- `tests/test_pass_condition.py`
- `tests/test_mock_teacher.py`
- `tests/test_mock_collector.py`
- `tests/test_export_policy_sft.py`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- `python3 scripts/collect_mock_episodes.py --num 5` - passed; saved 5 episodes.
- `python3 scripts/validate_episodes.py data/raw_episodes` - passed with 5 episodes and 0 errors.
- `python3 scripts/export_policy_sft.py` - passed; wrote 5 rows to `data/sft/retry_policy_sft_sharegpt.jsonl`.
- `python3 -m unittest discover tests` - passed with 19 tests.
- `python3 scripts/safe_check.py` - passed.
- `python3 -m compileall src scripts tests` - passed.

Blockers:

- None for mock collection. Real GPT-5.5 teacher and Qwen-Image-Edit adapters are scaffolded only and intentionally do not run in tests.

Next recommended step:

- Replace one mock adapter at a time in a controlled environment: first real Geneval evaluator, then real retry executor, then real GPT-5.5 teacher action generation.

## Qwen-Image And Geneval Batch Diagnostic Scaffold

Status: completed.

Completed work:

- Added a batch collector scaffold for Qwen-Image candidate generation plus Geneval evaluation.
- Designed the batch around the intended next data stage:
  - prompt;
  - 4 generated images per prompt;
  - raw Geneval JSON per image;
  - structured candidate diagnostics;
  - teacher-ready diagnostics for later GPT action GT construction.
- Added `scripts/collect_qwen_geneval_diagnostics.py`.
- Added `src/gen_retry/collectors/qwen_geneval_batch.py`.
- Added `src/gen_retry/evaluators/geneval_result_normalizer.py`.
- Added 10 pilot prompts at `data/prompts/geneval_pilot_10.jsonl`.
- Added `docs/QWEN_GENEVAL_BATCH.md` with A100 command-template examples.
- Added tests for Geneval result normalization and Qwen/Geneval batch planning.
- Ran plan-only mode for 10 prompts x 4 images, producing a 40-row generation manifest at `data/runs/qwen_geneval_pilot_10/generation_manifest.jsonl`.
- Did not run real Qwen-Image, Geneval, GPT teacher API, training, RL, or dependency installation.

Changed files:

- `README.md`
- `scripts/collect_qwen_geneval_diagnostics.py`
- `src/gen_retry/collectors/qwen_geneval_batch.py`
- `src/gen_retry/evaluators/geneval_result_normalizer.py`
- `data/prompts/geneval_pilot_10.jsonl`
- `data/runs/qwen_geneval_pilot_10/generation_manifest.jsonl`
- `docs/QWEN_GENEVAL_BATCH.md`
- `tests/test_geneval_result_normalizer.py`
- `tests/test_qwen_geneval_batch.py`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- `python3 scripts/collect_qwen_geneval_diagnostics.py --prompts data/prompts/geneval_pilot_10.jsonl --output-dir data/runs/qwen_geneval_pilot_10 --images-per-prompt 4 --gpus 0,1,2,3 --plan-only` - passed; planned 40 candidates.
- `python3 -m unittest tests.test_geneval_result_normalizer tests.test_qwen_geneval_batch` - passed with 4 tests.
- `python3 -m unittest discover tests` - passed with 23 tests.
- `python3 scripts/safe_check.py` - passed.
- `python3 -m compileall src scripts tests` - passed.

Blockers:

- None for scaffold/plan-only mode. Real generation/evaluation must be run in a prepared A100/Geneval environment by supplying command templates.

Next recommended step:

- On the A100 server, run `scripts/collect_qwen_geneval_diagnostics.py` with real Qwen-Image and Geneval command templates, inspect `candidate_diagnostics.jsonl`, then feed `teacher_diagnostics.jsonl` into `scripts/build_teacher_retry_actions.py`.

## Relay API Hygiene And Local Reference Repo Guard

Status: completed.

Completed work:

- Confirmed the user's OpenAI-compatible relay base URL is `https://skyapi.duckdns.org/v1`.
- Confirmed current API integration already separates decision teacher env vars from image-generation env vars.
- Added local reference-repo directory names to `.gitignore` so accidental in-repo copies of Gen-Searcher/GenEvolve are not committed or searched by default.
- Replaced `scripts/test.py` with a stdlib-only `/models` smoke helper that reads API keys from environment variables only.
- Removed hard-coded API key material from `scripts/test.py`.

Changed files:

- `.gitignore`
- `scripts/test.py`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- `rg -n "sk-[A-Za-z0-9_-]+" AGENTS.md README.md .env.example .gitignore configs docs examples schemas scripts src tests pyproject.toml index.html` - no matches.
- `python3 -m compileall src scripts tests` - passed.

Blockers:

- None for relay configuration hygiene. Real API execution still requires the user to provide keys through environment variables.

Next recommended step:

- In a normal terminal, export `GEN_RETRY_TEACHER_*` and `GEN_RETRY_IMAGE_*` with the relay URL and exact relay model IDs, then run a one-row smoke test before scaling.

## Geneval2 GPT-Teacher Smoke SFT

Status: completed.

Completed work:

- Loaded `.env` without printing API keys and confirmed the relay variables are present.
- Confirmed the relay lists both `gpt-5.5` and `gpt-image-2`.
- Extracted 3 Geneval2 prompt rows from `../GenEval2/geneval2_data.jsonl`.
- Extended `scripts/collect_mock_episodes.py` with `--teacher mock|gpt55|seed` so the latest `initial_plan`/`retry_replan` teacher can be tested with mock generation/evaluation.
- Ran 3 Geneval2 smoke episodes with real GPT-5.5 teacher and mock generator/evaluator.
- Verified every episode has the planner action sequence `initial_plan,retry_replan`.
- Exported 6 ShareGPT SFT rows, one `initial_plan` and one `retry_replan` sample per episode.
- Ran one standalone `gpt-image-2` image-generation adapter smoke test.
- Added HTTP retry handling for GPT teacher 429/5xx relay failures after the first smoke attempt hit a temporary 502 upstream error.

Changed files:

- `.gitignore`
- `scripts/collect_mock_episodes.py`
- `scripts/test.py`
- `src/gen_retry/teachers/gpt55_teacher_adapter.py`
- `data/prompts/geneval2_smoke_3.jsonl`
- `data/raw_episodes/geneval2_gpt55_smoke/*.json`
- `data/images/geneval2_gpt55_smoke/*`
- `data/images/api_smoke/gpt_image2_smoke.png`
- `data/images/api_smoke/gpt_image2_smoke.png.json`
- `data/sft/geneval2_gpt55_smoke_sharegpt.jsonl`
- `data/rejected/geneval2_gpt55_smoke_rejected.jsonl`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- `python3 scripts/prepare_geneval2_prompts.py --input ../GenEval2/geneval2_data.jsonl --output data/prompts/geneval2_smoke_3.jsonl --limit 3` - passed.
- `python3 scripts/test.py --contains gpt` with `.env` loaded - passed; relay listed `gpt-5.5` and `gpt-image-2`.
- `python3 scripts/collect_mock_episodes.py --prompts data/prompts/geneval2_smoke_3.jsonl --num 3 --teacher gpt55 --evaluator-type geneval2 --max-retry 1 --output-dir data/raw_episodes/geneval2_gpt55_smoke --image-dir data/images/geneval2_gpt55_smoke --resume` - passed; saved 3 episodes.
- `python3 scripts/validate_episodes.py data/raw_episodes/geneval2_gpt55_smoke` - passed with 3 episodes and 0 errors.
- `python3 scripts/export_sft.py --input data/raw_episodes/geneval2_gpt55_smoke --output data/sft/geneval2_gpt55_smoke_sharegpt.jsonl --rejected-output data/rejected/geneval2_gpt55_smoke_rejected.jsonl` - passed; exported 6 rows and 0 rejected rows.
- `python3 -m compileall src scripts tests` - passed.
- `python3 scripts/safe_check.py` - passed.
- `rg -n "sk-[A-Za-z0-9_-]+" AGENTS.md README.md .env.example .gitignore configs docs examples schemas scripts src tests pyproject.toml index.html` - no matches.

Blockers:

- Full real GenEval2 evaluation was not run in this smoke. The official evaluator loads Qwen3-VL-8B and should be run separately when ready for a heavier end-to-end test.

Next recommended step:

- Run a 1-prompt full path with `collect_real_episodes.py` using real `gpt-image-2` generation and the GenEval2 evaluator command template, then compare its SFT export against this mock-evaluator smoke output.

## Real Geneval2 Closed-Loop Smoke

Status: completed.

Completed work:

- Audited the real closed-loop path:
  - Geneval2 prompt loading;
  - GPT-5.5 `initial_plan`;
  - `gpt-image-2` generation;
  - Geneval2 atom-level evaluation;
  - Geneval2 normalization into `NormalizedEvalReport`;
  - rule-based stop/continue;
  - GPT-5.5 `retry_replan` when initial attempt fails;
  - regeneration from `retry_prompt`;
  - episode saving;
  - ShareGPT SFT export.
- Hardened `collect_real_episodes.py`:
  - safe default `--num 3`;
  - explicit `--allow-all` required for `--num 0`;
  - `--dry-run` mock mode that avoids real APIs/evaluator;
  - `--generator gpt_image2` alias.
- Tightened planner schemas so `initial_plan` and `retry_replan` reject extra keys.
- Expanded direct-image-edit rejection to include masks, boxes, bounding boxes, inpainting, source images, and edit instructions.
- Tightened teacher prompts for JSON-only, exact schema keys, no web/image/reference search, no direct edit, no invented constraints, and regeneration-only retry semantics.
- Added image API retry handling for 429/5xx relay failures.
- Normalized `GEN_RETRY_IMAGE_SIZE=None` / `GEN_RETRY_IMAGE_QUALITY=None` as unset.
- Fixed GenEval2 single-image wrapper to pass absolute image paths into the official evaluator subprocess.
- Sanitized episode-to-SFT export so retry planner user context excludes `image_path`, `image_id`, `raw_report`, `details.raw`, API logs, and raw Geneval2 rows.
- Adjusted local Python environment with user approval:
  - downgraded `huggingface-hub` from `1.20.1` to `0.36.2` to satisfy `transformers==4.57.0`;
  - installed `pytest==9.1.1`.
- Ran the real 3-prompt smoke with `--num 3 --max-retry 2 --pass-threshold 0.95`.

Real smoke outputs:

- Episodes: `data/raw_episodes_real_smoke/`
- SFT export: `data/sft/retry_sft_real_smoke.jsonl`
- Real generated images and Geneval2 atom outputs: `data/images/episode_*.png` and `data/images/episode_*.geneval2.json`

Real smoke metrics:

- Real episodes generated: 3.
- Images generated: 4.
- Geneval2 evaluations completed: 4.
- `initial_plan` SFT samples exported: 3.
- `retry_replan` SFT samples exported: 1.
- Final outcomes:
  - `episode_000000_172975eb2bc3`: `pass_without_retry`.
  - `episode_000001_d0db5e565544`: `passed_after_retry`.
  - `episode_000002_948e80ea1b67`: `pass_without_retry`.

Changed files:

- `.gitignore`
- `scripts/collect_real_episodes.py`
- `scripts/collect_mock_episodes.py`
- `scripts/run_geneval2_single_image.py`
- `scripts/test.py`
- `src/gen_retry/export/export_sft.py`
- `src/gen_retry/filters/filter_sft_samples.py`
- `src/gen_retry/filters/validate_episode.py`
- `src/gen_retry/generators/real_generator_adapter.py`
- `src/gen_retry/prompts/initial_plan_prompt.py`
- `src/gen_retry/prompts/retry_replan_prompt.py`
- `src/gen_retry/schemas/actions.py`
- `src/gen_retry/schemas/reports.py`
- `src/gen_retry/teachers/gpt55_teacher_adapter.py`
- `tests/test_actions.py`
- `tests/test_real_generator_adapter.py`
- `data/prompts/geneval2_smoke_3.jsonl`
- `data/raw_episodes_real_smoke/*.json`
- `data/sft/retry_sft_real_smoke.jsonl`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- `python3 scripts/collect_mock_episodes.py --num 5` - passed; saved 5 episodes.
- `python3 scripts/validate_episodes.py data/raw_episodes` - passed with 5 episodes and 0 errors.
- `python3 scripts/export_sft.py --input data/raw_episodes --output data/sft/retry_sft_mock_check.jsonl` - passed; exported 10 rows.
- `python3 -m pytest tests` - passed with 50 tests.
- `python3 -m unittest discover tests` - passed with 49 tests before pytest install.
- `python3 scripts/validate_episodes.py data/raw_episodes_real_smoke --strict-images` - passed with 3 episodes and 0 errors.
- `python3 scripts/export_sft.py --input data/raw_episodes_real_smoke --output data/sft/retry_sft_real_smoke.jsonl` - passed; exported 4 rows.
- Custom SFT/action audit - passed with 0 errors for direct edit fields and raw/image/API fields in SFT user context.
- `python3 scripts/safe_check.py` - passed.
- `python3 -m compileall src scripts tests` - passed.

Blockers:

- None for 3-prompt real smoke. Earlier attempts exposed and fixed:
  - `huggingface-hub` version incompatibility with `transformers`;
  - relative image paths inside the GenEval2 subprocess.

Next recommended step:

- Run a small scale-up, for example 10 Geneval2 prompts with the same real loop and `--max-retry 2`, then inspect retry frequency, evaluator runtime, and SFT row quality before larger collection.

## GenEval2 Static Difficulty Screening

Status: completed.

Completed work:

- Inspected local GenEval2 scoring docs and scripts:
  - atom scores are soft VQA probabilities on a 0-1 scale;
  - official total score is printed on a 0-100 scale;
  - Soft-TIFA AM is used for atom/per-skill analysis;
  - Soft-TIFA GM is used for prompt-level analysis and is very sensitive to any near-zero atom.
- Confirmed the 800 GenEval2 prompts are evenly distributed by `atom_count` 3 through 10, with 100 prompts per atom count.
- Added a static metadata-only difficulty selector that does not call image generation or evaluation APIs.
- Ranked prompts using static heuristics:
  - high atomicity;
  - multiple count atoms;
  - many object atoms;
  - multiple attributes;
  - position/spatial atoms;
  - verb/action atoms;
  - large number words;
  - harder material attributes;
  - multi-clause prompts.
- Wrote candidate prompt files for low-cost preselection before spending `gpt-image-2` calls.

Changed files:

- `scripts/select_geneval2_static_difficulty.py`
- `data/prompts/geneval2_static_hard_30.jsonl`
- `data/prompts/geneval2_static_medium_30.jsonl`
- `data/prompts/geneval2_static_verb_20.jsonl`
- `data/prompts/geneval2_static_position_20.jsonl`
- `data/prompts/geneval2_static_retry_candidates_25.jsonl`
- `docs/PROGRESS.md`

Validation commands run:

- `python3 scripts/select_geneval2_static_difficulty.py --output data/prompts/geneval2_static_hard_30.jsonl --limit 30 --bucket hard` - passed.
- `python3 scripts/select_geneval2_static_difficulty.py --output data/prompts/geneval2_static_medium_30.jsonl --limit 30 --bucket medium` - passed.
- `python3 scripts/select_geneval2_static_difficulty.py --output data/prompts/geneval2_static_verb_20.jsonl --limit 20 --require-skill verb` - passed.
- `python3 scripts/select_geneval2_static_difficulty.py --output data/prompts/geneval2_static_position_20.jsonl --limit 20 --require-skill position` - passed.
- `python3 -m compileall scripts/select_geneval2_static_difficulty.py` - passed.

Blockers:

- None. Static difficulty is only a proxy; true retry value still requires at least initial generation plus GenEval2 scoring.

Next recommended step:

- Use `data/prompts/geneval2_static_retry_candidates_25.jsonl` as the next low-cost candidate pool. Start with 5-10 rows, not the whole file, and measure initial failure rate plus retry success rate.

## Static Candidate Real Smoke 5

Status: completed.

Completed work:

- Ran the first 5 rows from `data/prompts/geneval2_static_retry_candidates_25.jsonl`.
- These first 5 rows were all `medium` static difficulty prompts with:
  - `atom_count=4`;
  - two count atoms;
  - two object atoms;
  - one spatial/position atom;
  - one attribute atom.
- Ran the full real loop:
  - GPT-5.5 `initial_plan`;
  - `gpt-image-2` generation;
  - Geneval2 evaluation;
  - rule-based stop;
  - episode save;
  - ShareGPT SFT export.
- No retry was triggered because every initial generation passed.

Outputs:

- Episodes: `data/raw_episodes_real_static_smoke_5/`
- Images/eval outputs: `data/images/real_static_smoke_5/`
- SFT export: `data/sft/retry_sft_real_static_smoke_5.jsonl`
- Rejected retry rows: `data/rejected/retry_replan_real_static_smoke_5_rejected.jsonl`

Metrics:

- Episodes generated: 5.
- Images generated: 5.
- Geneval2 evaluations completed: 5.
- Outcomes: 5 `pass_without_retry`.
- Retry triggered: 0.
- `initial_plan` SFT samples exported: 5.
- `retry_replan` SFT samples exported: 0.
- SFT raw/image/API field audit: 0 issues.
- Direct image edit action audit: 0 issues.

Per-prompt result:

- `a umbrella in front of a pink elephant`: score `1.0`, pass without retry.
- `a purple car in front of a bear`: score `0.998882`, pass without retry.
- `a trumpet in front of a sparkling chair`: score `0.999999`, pass without retry.
- `a sparkling mushroom to the right of a zebra`: score `1.0`, pass without retry.
- `a red trumpet to the right of a cookie`: score `1.0`, pass without retry.

Validation commands run:

- `python3 scripts/validate_episodes.py data/raw_episodes_real_static_smoke_5 --strict-images` - passed with 5 episodes and 0 errors.
- `python3 scripts/export_sft.py --input data/raw_episodes_real_static_smoke_5 --output data/sft/retry_sft_real_static_smoke_5.jsonl --rejected-output data/rejected/retry_replan_real_static_smoke_5_rejected.jsonl` - passed; exported 5 rows.
- `python3 -m compileall src scripts tests` - passed.
- Custom static-smoke analysis/audit - passed with 0 raw-field and 0 direct-edit issues.

Conclusion:

- The `medium` static bucket is too easy for `gpt-image-2` under the current planner prompts.
- Static difficulty based on single spatial relation plus low atomicity is not enough to produce retry data.
- For retry mining, skip these medium spatial prompts and move to hard prompts with large counts, multiple count atoms, multiple objects, or verb/action relations.

Next recommended step:

- Run a smaller hard-only batch, for example 5 rows from `data/prompts/geneval2_static_hard_30.jsonl`, or 3 rows from `data/prompts/geneval2_static_verb_20.jsonl` if API budget allows. Prefer hard large-count/count+position prompts before very-hard verb prompts.

## Geneval2 Atom Threshold + Tool Trajectory Export

Status: completed.

Completed work:

- Added configurable Geneval2 atom diagnostic threshold for training-data construction.
- Kept the existing compact JSON policy SFT export.
- Added explicit full-episode tool trajectory SFT export with only `query_skill`, `generate_image`, and `judge_image`.
- Added fixed skill guidance lookup for:
  - `object_presence`
  - `quantity_counting`
  - `attribute_binding`
  - `spatial_layout`
  - `anti_occlusion`
  - `multi_object_composition`
  - `clarity_visibility`
  - `negative_constraints`
- Added tool trajectory validation and a Geneval2 threshold audit script.
- Ran a capped real Geneval2 smoke with exactly 3 prompts, `--atom-threshold 0.90`, `--pass-threshold 0.95`, and `--max-retry 2`.

Changed files:

- `src/gen_retry/evaluators/geneval2_result_normalizer.py`
- `src/gen_retry/evaluators/geneval2_adapter.py`
- `src/gen_retry/export/export_sft.py`
- `src/gen_retry/skills/skill_library.py`
- `scripts/collect_real_episodes.py`
- `scripts/normalize_geneval2_results.py`
- `scripts/export_sft.py`
- `scripts/audit_geneval2_thresholds.py`
- `scripts/validate_tool_sft.py`
- `tests/test_geneval2_result_normalizer.py`
- `tests/test_export_sft.py`

Outputs:

- Mock compact SFT: `data/sft/retry_sft_mock_compact.jsonl`
- Mock tool SFT: `data/sft/retry_sft_mock_tool.jsonl`
- Real episodes: `data/raw_episodes_real_smoke_atom090/`
- Real images/evals: `data/images/real_smoke_atom090/`
- Real compact SFT: `data/sft/retry_sft_real_smoke_atom090_compact.jsonl`
- Real tool SFT: `data/sft/retry_sft_real_smoke_atom090_tool.jsonl`
- Real threshold audit: `data/analysis/geneval2_threshold_audit_real_atom090.json`

Validation commands run:

- `python3 scripts/collect_mock_episodes.py --num 5` - passed.
- `python3 scripts/validate_episodes.py data/raw_episodes` - passed with 5 episodes and 0 errors.
- `python3 scripts/export_sft.py --input data/raw_episodes --output data/sft/retry_sft_mock_compact.jsonl --format compact` - passed with 10 compact rows.
- `python3 scripts/export_sft.py --input data/raw_episodes --output data/sft/retry_sft_mock_tool.jsonl --format tool` - passed with 5 tool rows.
- `python3 scripts/export_sft.py --input data/raw_episodes --output data/sft/retry_sft_mock_both_compact.jsonl --tool-output data/sft/retry_sft_mock_both_tool.jsonl --format both` - passed.
- `python3 scripts/validate_tool_sft.py data/sft/retry_sft_mock_tool.jsonl` - passed.
- `python3 scripts/validate_tool_sft.py data/sft/retry_sft_mock_both_tool.jsonl` - passed.
- `python3 scripts/audit_geneval2_thresholds.py --input data/raw_episodes --thresholds 0.5,0.9,0.95 --output data/analysis/geneval2_threshold_audit_mock.json` - passed.
- `python3 -m compileall src scripts tests` - passed.
- `python3 -m pytest` - passed with 53 tests.
- Real smoke command with `data/prompts/geneval2_smoke_3.jsonl`, `--num 3`, `--max-retry 2`, `--pass-threshold 0.95`, and `--atom-threshold 0.90` - passed.
- `python3 scripts/validate_episodes.py data/raw_episodes_real_smoke_atom090` - passed with 3 episodes and 0 errors.
- Real compact/tool exports - passed with 3 rows each.
- `python3 scripts/validate_tool_sft.py data/sft/retry_sft_real_smoke_atom090_tool.jsonl` - passed.
- `python3 scripts/audit_geneval2_thresholds.py --input data/raw_episodes_real_smoke_atom090 --thresholds 0.5,0.9,0.95 --output data/analysis/geneval2_threshold_audit_real_atom090.json` - passed.

Real smoke metrics under `atom_threshold=0.90`:

- Episodes generated: 3.
- Generated images: 3.
- Geneval2 evaluations: 3.
- Retry replan actions: 0.
- Outcomes: 3 `pass_without_retry`.
- Failure type distribution: `{}`.
- Samples with no failed constraints: 3.
- Retry trigger rate: 0.0.

Blockers:

- None for the exporter or threshold plumbing.
- This particular 3-prompt smoke was too easy and did not produce retry samples.

Next recommended step:

- Use the hard prompt pool for retry mining, for example a capped 5-10 prompt run from `data/prompts/geneval2_static_hard_30.jsonl` with the same `--atom-threshold 0.90`, then inspect retry frequency before any larger 20-prompt collection.

## Hard Prompt Retry-Mining Checkpoint Atom 0.90

Status: completed.

Completed work:

- Ran the first 5 prompts from `data/prompts/geneval2_static_hard_30.jsonl`.
- Used `--atom-threshold 0.90`, `--pass-threshold 0.95`, and `--max-retry 2`.
- Exported both compact and tool trajectory SFT.
- Validated episodes and tool trajectories.
- Re-ran the Geneval2 threshold audit after fixing episode-dir grouping to use `episode_id:attempt_round` instead of merging repeated attempts by original prompt text.

Outputs:

- Episodes: `data/raw_episodes_real_hard_smoke_atom090_5/`
- Images/evals: `data/images/real_hard_smoke_atom090_5/`
- Compact SFT: `data/sft/retry_sft_real_hard_atom090_5_compact.jsonl`
- Tool SFT: `data/sft/retry_sft_real_hard_atom090_5_tool.jsonl`
- Threshold audit: `data/analysis/geneval2_threshold_audit_real_hard_atom090_5.json`

Metrics:

- Episodes: 5.
- Attempts / generated images / Geneval2 evals: 7.
- Episode retry rate: 1/5 = 20%.
- Retry replan actions: 2.
- Outcomes: 4 `pass_without_retry`, 1 `regressed`.
- Compact export rows: 5 `initial_plan` rows.
- Compact retry rows: 0, because both retry attempts were rejected as `regressed`.
- Tool trajectory rows: 5.
- Tool trajectory retry rows: 1 full regressed retry episode.
- Failure types across all attempts at atom threshold 0.90: `count_mismatch: 2`, `spatial_mismatch: 1`.
- First-attempt failure types: `count_mismatch: 1`.
- Thresholds seen in raw reports: `0.9`.

Important retry example:

- Episode: `data/raw_episodes_real_hard_smoke_atom090_5/episode_000003_df8642f2e8bb.json`
- Prompt: `seven backpacks on top of three sparkling flamingos`.
- Attempt 0 score: `0.96218`, failed `count_mismatch` for backpack count under atom threshold 0.90.
- Retry 1 score: `0.83332`, still failed backpack count.
- Retry 2 score: `0.85285`, failed `spatial_mismatch`; final outcome `regressed`.

Validation commands run:

- `python3 scripts/validate_episodes.py data/raw_episodes_real_hard_smoke_atom090_5` - passed with 5 episodes and 0 errors.
- `python3 scripts/export_sft.py --input data/raw_episodes_real_hard_smoke_atom090_5 --output data/sft/retry_sft_real_hard_atom090_5_compact.jsonl --format compact` - passed.
- `python3 scripts/export_sft.py --input data/raw_episodes_real_hard_smoke_atom090_5 --output data/sft/retry_sft_real_hard_atom090_5_tool.jsonl --format tool` - passed.
- `python3 scripts/validate_tool_sft.py data/sft/retry_sft_real_hard_atom090_5_tool.jsonl` - passed with 5 rows and 0 errors.
- `python3 scripts/audit_geneval2_thresholds.py --input data/raw_episodes_real_hard_smoke_atom090_5 --thresholds 0.5,0.9,0.95 --output data/analysis/geneval2_threshold_audit_real_hard_atom090_5.json` - passed.
- `python3 -m compileall scripts/audit_geneval2_thresholds.py` - passed.
- `python3 -m pytest` - passed with 53 tests.

Conclusion:

- The hard prompt pool is better than the medium pool for mining retry trajectories, but this 5-prompt slice still produced only one retry episode.
- The one retry episode is valuable for analysis and future RL-style negative feedback, but should not be used as a positive retry SFT target because both retry attempts regressed.
- Compact export is correctly filtering regressed retry actions.
- Tool trajectory export is structurally valid, but downstream training should filter or mask regressed retry trajectories unless intentionally training negative/stop behavior.

Next recommended step:

- Run a 20-prompt hard collection only as mining, not as final SFT. Keep all raw episodes, but include only `passed_after_retry` / `improved_after_retry` retry actions as positive SFT targets. Treat `regressed` episodes as analysis/RL data or negative examples with careful masking.

## Hard Prompt Next20 Retry Mining Atom 0.90

Status: completed.

Completed work:

- Resumed the interrupted 20-prompt hard mining run from 13 completed episodes.
- Used `data/prompts/geneval2_static_hard_next20.jsonl`.
- Kept the same real loop settings:
  - `--teacher gpt55`;
  - `--generator gpt_image2`;
  - `--evaluator geneval2`;
  - `--max-retry 2`;
  - `--pass-threshold 0.95`;
  - `--atom-threshold 0.90`.
- Completed all 20 raw episodes with real GPT-5.5 planning, GPT Image 2 generation, and GenEval2 evaluation.
- Exported compact positive-policy SFT rows and full tool-trajectory rows.
- Validated raw episodes, tool trajectories, threshold audit, safe checks, tests, and secret-pattern hygiene.

Outputs:

- Episodes: `data/raw_episodes_real_hard_atom090_next20/`
- Images/evals: `data/images/real_hard_atom090_next20/`
- Compact SFT: `data/sft/retry_sft_real_hard_atom090_next20_compact.jsonl`
- Tool SFT: `data/sft/retry_sft_real_hard_atom090_next20_tool.jsonl`
- Rejected retry rows: `data/rejected/retry_replan_real_hard_atom090_next20_rejected.jsonl`
- Threshold audit: `data/analysis/geneval2_threshold_audit_real_hard_atom090_next20.json`

Metrics:

- Episodes: 20.
- Attempts / generated images / GenEval2 evals: 27.
- Episodes with retry: 5/20.
- Retry attempts: 7.
- Outcomes: 15 `pass_without_retry`, 3 `passed_after_retry`, 2 `regressed`.
- Compact export rows: 23 total = 20 `initial_plan` rows + 3 positive `retry_replan` rows.
- Rejected retry rows: 4, all from `regressed` retry spans.
- Tool trajectory rows: 20, including the 2 regressed trajectories for analysis/RL-style feedback.
- Failure types across all attempts at atom threshold 0.90: `count_mismatch: 9`, `relation_mismatch: 3`.
- First-attempt failure types: `count_mismatch: 6`, `relation_mismatch: 1`.
- Threshold audit at atom threshold 0.90: 27 attempt groups, retry-trigger count 9, retry-trigger rate 0.333 by attempt group.

Important episodes:

- Positive retry SFT examples:
  - `episode_000003_d2ea02c7b4ab`: `five pink motorcycles and seven wooden raccoons`, passed after one retry.
  - `episode_000004_d337a72bf9f9`: `a brown flamingo and six cows and seven penguins`, passed after one retry.
  - `episode_000005_7a2c81f0956c`: `five plastic mushrooms and seven spotted trucks`, passed after one retry.
- Regressed analysis examples:
  - `episode_000013_0a241b6fa964`: `four trumpets and two brown trucks and four toys`, two retries, final `regressed`.
  - `episode_000019_c2572ed5e9de`: `seven penguins jumping over three kangaroos`, two retries, final `regressed`.

Validation commands run:

- `python3 scripts/validate_episodes.py data/raw_episodes_real_hard_atom090_next20 --strict-images` - passed with 20 episodes and 0 errors.
- `python3 scripts/export_sft.py --input data/raw_episodes_real_hard_atom090_next20 --output data/sft/retry_sft_real_hard_atom090_next20_compact.jsonl --tool-output data/sft/retry_sft_real_hard_atom090_next20_tool.jsonl --rejected-output data/rejected/retry_replan_real_hard_atom090_next20_rejected.jsonl --format both` - passed.
- `python3 scripts/validate_tool_sft.py data/sft/retry_sft_real_hard_atom090_next20_tool.jsonl` - passed with 20 rows and 0 errors.
- `python3 scripts/audit_geneval2_thresholds.py --input data/raw_episodes_real_hard_atom090_next20 --thresholds 0.5,0.9,0.95 --output data/analysis/geneval2_threshold_audit_real_hard_atom090_next20.json` - passed.
- `python3 scripts/safe_check.py` - passed.
- `python3 -m compileall src scripts tests` - passed.
- `python3 -m pytest` - passed with 53 tests.
- `rg -n "sk-[A-Za-z0-9_-]+" AGENTS.md README.md .env.example .gitignore configs docs examples schemas scripts src tests pyproject.toml index.html` - no matches.
- Manual spot-check of the 3 positive compact retry rows - passed:
  - all use `decision=regenerate`;
  - no mask, bounding box, inpainting, source-image, or direct-edit fields;
  - all repair `count_mismatch` by strengthening exact counts, visibility, separation, non-overlap, and negative constraints.

Conclusion:

- The next20 hard pool produced usable positive retry SFT data: 3 accepted retry-replan samples.
- The raw mining set is more useful than the earlier 5-prompt hard smoke because it contains both positive retry repairs and regressed multi-turn failures.
- Compact export is behaving correctly for the current SFT policy: it includes only positive retry actions and rejects regressed retry spans.
- Tool trajectories remain useful for analysis and future RL/negative-feedback work, but `final_outcome=regressed` tool rows should be filtered or masked for standard positive SFT.

Next recommended step:

- Inspect the 3 positive retry compact rows manually for teacher quality, then run another hard/verb-biased mining batch only if the accepted positive retry count is still too small for training.

## Offline GenEval2 Manual Transfer Planner

Status: completed.

Completed work:

- Reviewed the requested goal and confirmed it is compatible with the local safety rules: no sibling-repo writes, no dependency installation, no network sync, no training, and no large-scale generation.
- Added an offline Machine A -> Machine B -> Machine A data contract for manual transfer.
- Added candidate-level raw trajectory memory with fixed, persistent, new, and regressed constraint diffs.
- Added best-so-far tracking, score deltas, and branch-source metadata for retry replanning.
- Added rule-based stop logic for `passed`, `max_retry`, `no_improvement`, `large_regression`, and `invalid_teacher_action`.
- Patched teacher retry context to include full `previous_action`, current eval report, best-so-far object, retry memory, score deltas, and available skills.
- Patched `RetryReplanAction` and JSON schema with `branch_source` and `branch_source_round`.
- Patched compact SFT retry export so step-level input includes memory fields while still excluding local `image_path` from trainable/context JSON.
- Added stdlib validation for offline input packages, retry action packages, and raw trajectories.
- Added a Chinese operation/report document for the offline GenEval2 retry pipeline.

Changed files:

- `src/gen_retry/offline_planner.py`
- `scripts/offline_evaluate_and_plan.py`
- `scripts/validate_offline_retry_package.py`
- `src/gen_retry/schemas/actions.py`
- `src/gen_retry/prompts/retry_replan_prompt.py`
- `src/gen_retry/teachers/gpt55_teacher_adapter.py`
- `src/gen_retry/teachers/mock_teacher.py`
- `src/gen_retry/collectors/collect_episodes.py`
- `src/gen_retry/export/export_sft.py`
- `schemas/teacher_retry_action.schema.json`
- `tests/test_actions.py`
- `tests/test_offline_planner.py`
- `docs/OFFLINE_GENEVAL2_RETRY_PIPELINE.md`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- `python3 -m compileall src scripts tests` - passed.
- `python3 -m unittest tests.test_actions tests.test_offline_planner tests.test_export_sft` - passed with 10 tests.
- `python3 -m unittest tests.test_actions tests.test_offline_planner` - passed with 7 tests after moving the new offline planner test temp directory inside the repo.
- `python3 -m json.tool schemas/teacher_retry_action.schema.json >/dev/null` - passed.
- `python3 scripts/safe_check.py` - passed.
- `git diff --check -- src/gen_retry/offline_planner.py scripts/offline_evaluate_and_plan.py scripts/validate_offline_retry_package.py src/gen_retry/schemas/actions.py src/gen_retry/prompts/retry_replan_prompt.py src/gen_retry/teachers/gpt55_teacher_adapter.py src/gen_retry/teachers/mock_teacher.py src/gen_retry/collectors/collect_episodes.py src/gen_retry/export/export_sft.py schemas/teacher_retry_action.schema.json tests/test_actions.py tests/test_offline_planner.py docs/OFFLINE_GENEVAL2_RETRY_PIPELINE.md docs/PROGRESS.md docs/CODEX_HANDOFF.md` - passed.

Blockers:

- None for the offline contract/planner implementation.
- Real `gpt55` teacher calls still require the user to set `GEN_RETRY_TEACHER_*` in a controlled environment. Local validation can use `--teacher mock`.

Next recommended step:

- Run one manual-transfer smoke package with `--teacher mock`, validate the input/output/trajectory JSON, then repeat with `--teacher gpt55` in the controlled API environment.

## GenEval2 Qwen-Image 100 Prompt Pilot Kickoff

Status: in progress.

Completed work:

- Reviewed the latest goal: prioritize 100 GenEval2 prompts x 5 Qwen-Image-2512 initial candidates before the slower teacher/eval/retry stages, with visible total progress and ETA.
- Added balanced GenEval2 prompt selection:
  - `scripts/select_balanced_geneval2_prompts.py`
  - output: `data/prompts/geneval2_balanced_100.jsonl`
  - summaries: `data/prompts/geneval2_balanced_100.summary.json` and `.summary.md`
- Added a stdlib progress meter:
  - `src/gen_retry/utils/progress.py`
- Added resumable teacher initial-plan precompute:
  - `scripts/precompute_initial_plans.py`
- Added GenEval2 batch evaluation preparation:
  - `scripts/run_geneval2_batch.py`
  - supports official Qwen image layout, `--plan-only`, partial validation, raw score lists, atom rows, and normalized reports.
- Added pilot artifact validation:
  - `scripts/validate_geneval2_pilot_state.py`
  - validates prompts, image layout, manifest, initial-plan cache, GenEval2 normalized reports, and latest generation progress from logs.
- Patched Qwen generation and command-template collection to print total progress/ETA:
  - `scripts/generate_qwen_geneval_images.py`
  - `scripts/collect_qwen_geneval_diagnostics.py`
  - `src/gen_retry/collectors/qwen_geneval_batch.py`
- Patched candidate ids to use `prompt_id`, so 500 candidates follow `prompt_id_cand_XX`.
- Built a 500-row plan-only manifest:
  - `data/qwen_geneval2_balanced_100_x5_manifest/generation_manifest.jsonl`
- Ran a real Qwen smoke with `../models/Qwen-Image-2512`; 1 image completed successfully.
- Started the full 100 x 5 generation run with `setsid`:
  - parent PID file: `data/run_logs/qwen_geneval2_balanced_100_x5.pid`
  - log: `data/run_logs/qwen_geneval2_balanced_100_x5.log`
  - output dir: `data/qwen_geneval2_balanced_100_x5_images/`

Current run status at checkpoint:

- Parent PID: `1036`.
- Child worker PID: `1042`.
- Current completed images observed: `13/500`.
- Shard-level ETA after thirteen images: about `10:35:29`.
- GPU was active at 100% during generation.
- Parent total ETA is noisy during the first few images because it includes model loading time; shard-level ETA is the better early estimate.

Validation commands run:

- `python3 scripts/select_balanced_geneval2_prompts.py --input ../GenEval2/geneval2_data.jsonl --output data/prompts/geneval2_balanced_100.jsonl --num-prompts 100` - passed, wrote 100 rows.
- `python3 scripts/collect_qwen_geneval_diagnostics.py --prompts data/prompts/geneval2_balanced_100.jsonl --output-dir data/qwen_geneval2_balanced_100_x5_manifest --images-per-prompt 5 --gpus 0 --qwen-model-path ../models/Qwen-Image-2512 --plan-only --limit 100` - passed, wrote 500 candidate rows.
- `python3 -m compileall src scripts tests` - passed.
- Prompt JSONL and manifest were parsed with stdlib `json`; row counts are 100 and 500.
- `git diff --check -- scripts/select_balanced_geneval2_prompts.py scripts/generate_qwen_geneval_images.py scripts/collect_qwen_geneval_diagnostics.py src/gen_retry/collectors/qwen_geneval_batch.py src/gen_retry/utils/progress.py` - passed.
- `python3 scripts/precompute_initial_plans.py --prompts data/prompts/geneval2_balanced_100.jsonl --output-dir data/plans/initial_mock_balanced_100 --teacher mock --num-workers 4 --resume --progress-interval 5` - passed with 100 mock plan caches and 0 errors.
- `python3 scripts/run_geneval2_batch.py --metadata data/prompts/geneval2_balanced_100.jsonl --image-dir data/qwen_geneval2_balanced_100_x5_images --output-dir data/geneval2/qwen_geneval2_balanced_100_x5_plan --n-samples 5 --limit 100 --allow-partial --plan-only` - passed; at run time it saw 7 existing image jobs and 493 missing images, without starting GenEval2.
- `python3 scripts/validate_geneval2_pilot_state.py --prompts data/prompts/geneval2_balanced_100.jsonl --image-dir data/qwen_geneval2_balanced_100_x5_images --manifest data/qwen_geneval2_balanced_100_x5_manifest/generation_manifest.jsonl --plan-dir data/plans/initial_mock_balanced_100 --run-log data/run_logs/qwen_geneval2_balanced_100_x5.log --expected-prompts 100 --images-per-prompt 5 --allow-partial-images --output data/analysis/geneval2_qwen_pilot_state_partial.json` - passed with warning-only partial state: 13 existing images, 487 missing images, 100 valid mock initial plans, 0 errors.

Monitor commands:

- `tail -f data/run_logs/qwen_geneval2_balanced_100_x5.log`
- `find data/qwen_geneval2_balanced_100_x5_images -path '*/samples/*.png' -type f | wc -l`
- `ps -p "$(cat data/run_logs/qwen_geneval2_balanced_100_x5.pid)" -o pid=,ppid=,stat=,etime=,cmd=`
- `nvidia-smi`

Blockers:

- None for initial generation. The full 500-image run is still in progress.
- Next stages still need implementation or orchestration: GenEval2 evaluation over generated images, teacher retry planning, retry generation, retry evaluation, and final SFT export for this pilot.

Next recommended step:

- Let the 500-image generation finish, then validate every manifest image path exists and start GenEval2 evaluation over the completed image layout.

## Geneval2 Balanced 100 GPT Teacher Initial Plans

Status: completed.

Completed work:

- Loaded local `.env` for `GEN_RETRY_TEACHER_*` without printing API keys.
- Verified the OpenAI-compatible relay `/models` endpoint was reachable and that `gpt-5.5` was available.
- Ran a 1-row real teacher initial-plan smoke successfully.
- Ran real GPT teacher initial-plan precompute for all 100 rows in `data/prompts/geneval2_balanced_100.jsonl`.
- Used `--resume`, so the smoke row was skipped and the remaining 99 rows completed with 0 errors.
- Wrote 100 valid initial-plan cache files under `data/plans/initial/geneval2_balanced_100_gpt55/`.
- Left `data/plans/initial/geneval2_balanced_100_gpt55/_errors/` in place as historical failed-attempt logs; the successful current outputs are the 100 JSON files in the parent plan directory.

Changed files:

- `data/plans/initial/geneval2_balanced_100_gpt55/*.json`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- Relay `/models` smoke via stdlib `urllib` - passed; target model `gpt-5.5` present.
- `python3 scripts/precompute_initial_plans.py --prompts data/prompts/geneval2_balanced_100.jsonl --output-dir data/plans/initial/geneval2_balanced_100_gpt55 --teacher gpt55 --evaluator-type geneval2 --num-workers 1 --limit 1 --progress-interval 0` - passed with 1/1 valid plan.
- `python3 scripts/precompute_initial_plans.py --prompts data/prompts/geneval2_balanced_100.jsonl --output-dir data/plans/initial/geneval2_balanced_100_gpt55 --teacher gpt55 --evaluator-type geneval2 --num-workers 4 --resume --progress-interval 30` - passed with 99/99 successful API calls and 0 errors.
- `find data/plans/initial/geneval2_balanced_100_gpt55 -maxdepth 1 -type f -name '*.json' | wc -l` - returned 100.
- Custom stdlib schema check over all 100 prompt IDs and `InitialPlanAction` payloads - passed with 100 valid, 0 missing, 0 invalid.
- `python3 -m compileall src scripts tests` - passed.

Blockers:

- None for teacher initial-plan precompute.

Next recommended step:

- Use `data/plans/initial/geneval2_balanced_100_gpt55/` as the real initial-plan cache for the 100-prompt pilot; after the 500 initial images finish, run GenEval2 evaluation and then decide which failed candidates need teacher retry replanning.

## GenEval2 Retry SFT Goal Outline

Status: completed.

Completed work:

- Read Gen-Searcher Qwen image references as read-only.
- Confirmed Gen-Searcher contains a Qwen image edit service based on `QwenImageEditPlusPipeline`, not the exact current Qwen-Image-2512 text-to-image batch path.
- Extracted relevant Gen-Searcher generation defaults: `num_inference_steps=40`, `true_cfg_scale=4.0`, `guidance_scale=1.0`, `negative_prompt=" "`, one image per request, one loaded pipeline per GPU with serialized per-GPU scheduling.
- Wrote a concise persistent project goal and workflow outline for the GenEval2 retry SFT pilot.
- Recorded that current `generate_qwen_geneval_images.py` reads `metadata.prompt`; plan-conditioned generation needs either an `--initial-plan-dir` extension or derived metadata using `initial_plan.initial_prompt` while preserving original metadata for GenEval2.

Changed files:

- `docs/GENEVAL2_RETRY_SFT_GOAL.md`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- Read-only `rg`/`sed` inspection of Gen-Searcher Qwen image API and workflow files.

Blockers:

- None for the outline.

Next recommended step:

- Superseded by the current plan-conditioned generation update: `scripts/generate_qwen_geneval_images.py` now supports `--initial-plan-dir`.

## Qwen Generation Prompt Suffix And Image Git Ignore

Status: completed.

Completed work:

- Changed `scripts/generate_qwen_geneval_images.py --positive-suffix` default from `, Ultra HD, 4K, cinematic composition.` to an empty string.
- Updated pilot docs so recommended generation commands no longer append a style suffix by default.
- Added `.gitignore` rules for generated image file types under `data/`.
- Removed already tracked `data/**/*.png` files from the Git index with `git rm --cached`, while keeping the local image files on disk.

Changed files:

- `.gitignore`
- `scripts/generate_qwen_geneval_images.py`
- `docs/GENEVAL2_RETRY_SFT_GOAL.md`
- `docs/GENEVAL2_QWEN_PILOT_100_REPORT.md`
- `docs/CODEX_HANDOFF.md`
- `docs/PROGRESS.md`
- Git index now records removal of previously tracked `data/**/*.png` files.

Validation commands run:

- `python3 -m compileall scripts/generate_qwen_geneval_images.py` - passed.
- `python3 scripts/generate_qwen_geneval_images.py --help` - passed and reports `--positive-suffix` defaults to empty.
- `git check-ignore -v --no-index data/qwen_geneval2_balanced_100_x5_images/00000/samples/00000.png data/images/episode_000000_30e93888ca3f_attempt_0.png` - matched `.gitignore` image rules.
- `git ls-files 'data/**/*.png' 'data/**/*.jpg' 'data/**/*.jpeg' 'data/**/*.webp' 'data/**/*.gif' | wc -l` - returned 0.
- Local image existence spot-check passed after `git rm --cached`.

Blockers:

- None.

Next recommended step:

- Patch plan-conditioned initial generation before the 4-GPU run, so the generator uses cached `initial_plan.initial_prompt` without any extra style suffix.

## GenEval2 Balanced-100 x5 Candidate Retry Trajectory Build

Status: completed.

Completed work:

- Ran GenEval2 over all 500 existing initial images (100 prompts x 5 candidates) using 4 parallel shards.
- Merged shard outputs into `data/geneval2_jobs/balanced100_all_candidates/` with 500 diagnostic jobs, 500 normalized reports, and 5,180 atom rows.
- Built 500 candidate-level generation packages with real initial-plan context and normalized GenEval2 diagnostics.
- Called the teacher retry API for every failed candidate and wrote 500 raw trajectories:
  - `initial_success`: 29
  - `retry_ready`: 471
  - `error`: 0
- Exported 471 retry-replan SFT rows; the 29 rejected rows are the initial-pass samples without retry targets.
- Generated the final Chinese report and JSON summary.

Important API note:

- The main teacher retry pass used the OpenAI-compatible relay with `gpt-5.5`.
- During the final tail batch, `gpt-5.5` returned HTTP 503 for 32 candidates. `/models` still worked, and a minimal `gpt-5.5` chat request also returned 503.
- Those 32 candidates were retried through the same relay with `gpt-5.4`, which completed successfully. The final dataset is complete, but 32 retry actions are from the fallback model.

Key outputs:

- Merged GenEval2 diagnostics: `data/geneval2_jobs/balanced100_all_candidates/normalized_reports.jsonl`
- Package manifest: `data/incoming_generation_results/geneval2_balanced_100x5_round0_with_eval/package_manifest.jsonl`
- Retry action manifest: `data/outgoing_retry_actions/geneval2_balanced_100x5_round0_gpt55/retry_action_manifest.jsonl`
- Raw trajectories: `data/raw_trajectories/geneval2_balanced_100x5_round0_gpt55/`
- SFT JSONL: `data/sft/geneval2_balanced_100x5_round0_retry_replan_sft.jsonl`
- Rejected SFT audit: `data/rejected/geneval2_balanced_100x5_round0_retry_replan_rejected.jsonl`
- Chinese report: `docs/GENEVAL2_BALANCED100_RETRY_TRAJECTORY_REPORT.md`
- Summary JSON: `data/analysis/geneval2_balanced100_retry_stage_summary.json`

Validation commands run:

- `python3 scripts/merge_geneval2_shards.py --shard-glob 'data/geneval2_jobs/balanced100_all_candidates_shards4/shard_*' --output-dir data/geneval2_jobs/balanced100_all_candidates --expected-count 500` - passed.
- `python3 scripts/prepare_geneval2_retry_inputs.py ... --all-candidates --limit 500` - passed with 500 packages, 500 eval reports, 29 pass, 471 retry candidates.
- `python3 scripts/rebuild_retry_action_manifest.py --output-dir data/outgoing_retry_actions/geneval2_balanced_100x5_round0_gpt55 --expected-count 500` - passed with 500 packages and 0 quality critical issues.
- `python3 scripts/export_offline_retry_sft.py --trajectories-dir data/raw_trajectories/geneval2_balanced_100x5_round0_gpt55 --output data/sft/geneval2_balanced_100x5_round0_retry_replan_sft.jsonl --rejected-output data/rejected/geneval2_balanced_100x5_round0_retry_replan_rejected.jsonl` - wrote 471 SFT rows.
- `python3 scripts/report_geneval2_retry_stage.py ... --all-candidates --limit 500` - passed and wrote the final report/summary.
- `python3 -m compileall src scripts tests` - passed.
- `python3 -m unittest discover tests` - passed, 70 tests.
- `python3 scripts/safe_check.py` - passed.
- `python3 -m json.tool` on the final summary, manifest rebuild summary, and merge summary - passed.
- `rg -n '<api-key-prefix>' .` - returned no matches; the API key was not written into repo files.
- Final count audit returned 500 reports, 500 package rows, 500 retry action manifest rows, 500 raw trajectories, 471 SFT rows, and 29 rejected initial-success rows.
- `git diff --check` - passed.

Blockers:

- None for this stage. `gpt-5.5` had a temporary 503 outage near the end; the 32 affected candidates were completed with `gpt-5.4` fallback.

Next recommended step:

- Use the 471 retry-ready trajectories for SFT filtering/training review, or start the next stage that actually generates retry images from `retry_ready_action.retry_prompt`.

## Retry Generation Git/Handoff Prep

Status: completed.

Completed work:

- Added a code-only/data-light Git ignore policy:
  - `data/**` is ignored by default.
  - `data/prompts/**` remains trackable for small prompt and handoff metadata files.
  - selected `.gitkeep` placeholders remain trackable.
- Added `scripts/export_retry_generation_metadata.py`.
- Exported the 471 retry-ready teacher plans into:
  - `data/prompts/geneval2_balanced_100x5_round1_retry_generation.jsonl`
- This metadata keeps the original GenEval2 prompt in `prompt` and stores the teacher retry plan in `generation_prompt`, so Qwen generation uses the retry plan while later GenEval2 evaluation still uses the original task prompt.
- The metadata now carries the original failed candidate seed in `seed` with `seed_source=initial_generation`.
- `scripts/generate_qwen_geneval_images.py` now prioritizes `metadata.seed`; if absent, it falls back to the previous `--seed + prompt_index * n_samples + candidate_index` formula.

Changed files:

- `.gitignore`
- `scripts/export_retry_generation_metadata.py`
- `scripts/generate_qwen_geneval_images.py`
- `data/prompts/geneval2_balanced_100x5_round1_retry_generation.jsonl`
- `tests/test_generate_qwen_geneval_images.py`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- `python3 -m compileall scripts/export_retry_generation_metadata.py` - passed.
- `python3 scripts/export_retry_generation_metadata.py --help` - passed.
- `python3 scripts/export_retry_generation_metadata.py --trajectories-dir data/raw_trajectories/geneval2_balanced_100x5_round0_gpt55 --output data/prompts/geneval2_balanced_100x5_round1_retry_generation.jsonl --retry-round 1` - wrote 471 rows.
- `wc -l data/prompts/geneval2_balanced_100x5_round1_retry_generation.jsonl` - returned 471.
- Metadata audit returned 471 rows, 0 missing seeds, and 471 unique paired seeds.
- `python3 -m unittest tests.test_generate_qwen_geneval_images` - passed.
- `git check-ignore -v --no-index data/prompts/geneval2_balanced_100x5_round1_retry_generation.jsonl data/geneval2_jobs/balanced100_all_candidates/normalized_reports.jsonl data/sft/geneval2_balanced_100x5_round0_retry_replan_sft.jsonl` - confirmed prompts are unignored and generated eval/SFT artifacts are ignored.
- `git diff --check -- .gitignore scripts/export_retry_generation_metadata.py scripts/generate_qwen_geneval_images.py tests/test_generate_qwen_geneval_images.py docs/PROGRESS.md docs/CODEX_HANDOFF.md` - passed.

Blockers:

- Existing tracked `data/` artifacts are still in the Git index until a separate `git rm --cached` cleanup is run. `.gitignore` prevents new artifact additions, but it does not untrack files already committed.

Next recommended step:

- For the remote generation machine, commit/push code plus `data/prompts/geneval2_balanced_100x5_round1_retry_generation.jsonl`, then run Qwen generation with `--metadata` pointing to that file and without `--initial-plan-dir`.
- For a clean long-term repo, run an intentional cached-index cleanup for generated `data/` artifacts before committing the Git hygiene change.

## Two-Machine Git Exchange Loop

Status: completed.

Completed work:

- Added `data/exchange/` as the tracked lightweight handoff area:
  - `data/exchange/api_to_gpu/` for API-machine generation metadata.
  - `data/exchange/gpu_to_api/` for GPU-machine GenEval2 handoff packages.
- Kept normal generated artifacts ignored under `data/**`; only `data/prompts/**` and `data/exchange/**` are trackable.
- Added `src/gen_retry/exchange.py` with two loop helpers:
  - GPU -> API: package `generation_manifest.jsonl`, `normalized_reports.jsonl`, optional `diagnostic_jobs.jsonl`, and summary files without images.
  - API continuation: turn a GPU handoff back into generation packages that preserve the original trajectory/candidate identity.
- Added `scripts/package_geneval2_handoff.py` for the GPU machine after GenEval2 merge.
- Added `scripts/build_retry_continuation_packages.py` for the API machine before calling teacher retry again.
- Updated retry generation metadata export to include the exact `previous_action` used for that retry prompt.
- Added `tests/test_exchange.py` covering candidate coverage and trajectory identity preservation.

Changed files:

- `.gitignore`
- `data/exchange/README.md`
- `data/exchange/api_to_gpu/.gitkeep`
- `data/exchange/gpu_to_api/.gitkeep`
- `scripts/export_retry_generation_metadata.py`
- `scripts/package_geneval2_handoff.py`
- `scripts/build_retry_continuation_packages.py`
- `src/gen_retry/exchange.py`
- `tests/test_exchange.py`
- `docs/PROGRESS.md`
- `docs/CODEX_HANDOFF.md`

Validation commands run:

- `python3 -m compileall src/gen_retry/exchange.py scripts/package_geneval2_handoff.py scripts/build_retry_continuation_packages.py scripts/export_retry_generation_metadata.py tests/test_exchange.py` - passed.
- `python3 -m unittest tests.test_exchange` - passed.
- `python3 -m unittest tests.test_generate_qwen_geneval_images` - passed.
- `git diff --check` - passed.
- `python3 -m compileall src scripts tests` - passed.
- `python3 scripts/package_geneval2_handoff.py --help` - passed.
- `python3 scripts/build_retry_continuation_packages.py --help` - passed.
- `git add -n data/exchange/README.md data/exchange/api_to_gpu/.gitkeep data/exchange/gpu_to_api/.gitkeep src/gen_retry/exchange.py scripts/package_geneval2_handoff.py scripts/build_retry_continuation_packages.py tests/test_exchange.py` - confirmed new exchange files are addable.

Blockers:

- None.

Next recommended step:

- On the GPU machine, after the current round1 GenEval2 merge finishes, run `scripts/package_geneval2_handoff.py` into `data/exchange/gpu_to_api/<run>/`, commit that directory, then pull it on the API machine and run `scripts/build_retry_continuation_packages.py` followed by `scripts/build_geneval2_retry_plans.py`.

## Round1 Retry Eval To Round2 Teacher Plans

Status: completed.

Completed work:

- Pulled GPU-machine handoff `data/exchange/gpu_to_api/balanced100x5_round1_retry_gpt55_v2/`.
- Verified handoff completeness:
  - `generation_manifest.jsonl`: 471 rows.
  - `normalized_reports.jsonl`: 471 rows.
  - `diagnostic_jobs.jsonl`: 471 rows.
  - `handoff_manifest.json`: status `ok`.
- Built API-side continuation packages:
  - `data/incoming_generation_results/balanced100x5_round1_retry_gpt55_v2_with_eval/`
  - 471 packages, 0 failures.
- Called `gpt-5.5` teacher retry API for all non-stopped round1 samples using 8 package shards.
- Rebuilt final retry action manifest:
  - `data/outgoing_retry_actions/balanced100x5_round1_retry_gpt55_v2/retry_action_manifest.jsonl`
  - 471 rows, 0 quality critical issues.
- Exported next GPU generation metadata:
  - `data/exchange/api_to_gpu/balanced100x5_round2_retry_gpt55_v2/generation_metadata.jsonl`
  - 396 rows for round2 retry generation.

Round1 outcome relative to round0:

- Total retry images evaluated: 471.
- Round0 average score: 0.7522.
- Round1 average score: 0.7715.
- Average delta: +0.0193.
- Improved: 279.
- Worse: 192.
- Same: 0.
- Passed after round1: 37.

Round1 teacher/stop outcome:

- `passed`: 37.
- `large_regression`: 38.
- continuing `retry_ready`: 396.
- `gpt-5.5` retry API calls: 396.
- API failures: 0.

Validation commands run:

- `python3 scripts/build_retry_continuation_packages.py ... --round 1 ...` - wrote 471 packages, 0 failures.
- `python3 scripts/test.py --contains gpt-5.5` - relay listed `gpt-5.5`.
- `python3 scripts/build_geneval2_retry_plans.py ... --teacher gpt55 --max-retry 3 --resume` over 8 package shards - all shards status `ok`.
- `python3 scripts/rebuild_retry_action_manifest.py --output-dir data/outgoing_retry_actions/balanced100x5_round1_retry_gpt55_v2 --expected-count 471` - status `ok`, 471 packages, 0 critical quality issues.
- `python3 scripts/export_retry_generation_metadata.py --trajectories-dir data/raw_trajectories/geneval2_balanced_100x5_round0_gpt55 --output data/exchange/api_to_gpu/balanced100x5_round2_retry_gpt55_v2/generation_metadata.jsonl --retry-round 2` - wrote 396 rows.
- Round2 metadata audit returned 396 rows, 0 missing `vqa_list`, 0 missing seed, 0 missing `previous_action`.

Blockers:

- None.

Next recommended step:

- Commit/push `data/exchange/api_to_gpu/balanced100x5_round2_retry_gpt55_v2/generation_metadata.jsonl` plus any desired code/doc updates, then GPU machine can generate round2 images from that metadata.

## Round2 Retry Eval To Round3 Teacher Plans

Status: completed.

Completed work:

- Consumed GPU-machine handoff `data/exchange/gpu_to_api/balanced100x5_round2_retry_gpt55_v2/` with 396 generation/eval rows.
- Built 396 round2 continuation packages with 0 package build failures.
- Called `gpt-5.5` teacher retry API for round2 samples. Initial parallel run hit 73 transient upstream HTTP 502 failures; targeted reruns reduced invalid teacher actions to 0.
- Rebuilt final manifest:
  - `data/outgoing_retry_actions/balanced100x5_round2_retry_gpt55_v2/retry_action_manifest.jsonl`
  - 396 rows, 0 quality critical issues.
- Exported round3 GPU metadata:
  - `data/exchange/api_to_gpu/balanced100x5_round3_retry_gpt55_v2/generation_metadata.jsonl`
  - 345 rows, 0 missing `vqa_list`, seed, or `previous_action`.

Round2 outcome relative to round1:

- Paired samples: 396.
- Average delta: +0.007744.
- Median delta: +0.005039.
- Improved: 220.
- Worse: 176.
- Passed after round2: 23.
- Stopped due large regression: 28.
- Continuing to round3: 345.

100x5 sampling audit:

- 100 prompts, exactly 5 candidates each.
- Round0 initial generation: 29 passed, 471 failed.
- 92/100 prompts had multiple failed-constraint signatures across the 5 candidates.
- 71/100 prompts had multiple failure-type signatures; 68/100 had multiple skill signatures.
- Average unique failed-constraint signatures per prompt: 3.01.

Validation commands run:

- `python3 scripts/build_retry_continuation_packages.py ... --round 2 ...` - wrote 396 packages, 0 failures.
- `python3 scripts/build_geneval2_retry_plans.py ... --teacher gpt55 --max-retry 3` over 8 shards plus targeted 502 reruns - final invalid teacher actions: 0.
- `python3 scripts/rebuild_retry_action_manifest.py --output-dir data/outgoing_retry_actions/balanced100x5_round2_retry_gpt55_v2 --expected-count 396` - status `ok`.
- `python3 scripts/export_retry_generation_metadata.py --trajectories-dir data/raw_trajectories/geneval2_balanced_100x5_round0_gpt55 --output data/exchange/api_to_gpu/balanced100x5_round3_retry_gpt55_v2/generation_metadata.jsonl --retry-round 3` - wrote 345 rows.
- Secret scan for the provided API key outside `.env` and `data/api_logs/**` returned no matches.

Blockers:

- None. The relay had transient HTTP 502s, but targeted reruns completed all teacher actions.

Next recommended step:

- Commit/push `data/exchange/api_to_gpu/balanced100x5_round3_retry_gpt55_v2/generation_metadata.jsonl` and pull on the GPU machine for round3 image generation.

## Round3 Review And Selective Canonical Round4 Plans

Status: completed.

Completed work:

- Consumed GPU-machine handoff `data/exchange/gpu_to_api/balanced100x5_round3_retry_gpt55_v2/` with 345 generation/eval rows.
- Reviewed round3 against round2: 345 paired samples, average delta -0.005068, median delta +0.000014, 176 improved, 169 worse, 15 passed by zero failed constraints, 29 large regressions.
- Added optional retry prompt style switch `GEN_RETRY_REPLAN_STYLE=canonical_display`; default behavior is unchanged.
- Built 345 round3 continuation packages with 0 failures.
- Selected 64 high-potential/control samples for a selective round4 teacher test:
  - 40 `best_so_far_promising`
  - 12 `latest_control`
  - 12 `count_hard_control`
- Ran `gpt-5.5` teacher retry with canonical display planning enabled over 4 shards:
  - 64/64 teacher actions
  - 0 API/package failures
  - 0 quality critical issues
- Exported selective round4 GPU metadata:
  - `data/exchange/api_to_gpu/balanced100x5_round4_retry_gpt55_v2_selective_canonical/generation_metadata.jsonl`
  - 64 rows, 0 missing `vqa_list`, seed, generation prompt, or previous action.

Canonical style check:

- Average retry prompt length: 142.3 words, shorter than the previous full round3 average.
- Prompt terms show intended planning style: `plain` 64/64, `row` 54/64, `background` 42/64, `band` 27/64, `visible` 63/64, `countable` 45/64.

Validation commands run:

- `python3 -m compileall src/gen_retry/prompts/retry_replan_prompt.py` - passed.
- `python3 scripts/build_retry_continuation_packages.py ... --round 3 ...` - wrote 345 packages, 0 failures.
- Selective package manifest build - wrote 64 selected rows.
- `python3 scripts/build_geneval2_retry_plans.py ... --teacher gpt55 --max-retry 4` over 4 selective shards with `GEN_RETRY_REPLAN_STYLE=canonical_display` - all shards status `ok`.
- `python3 scripts/rebuild_retry_action_manifest.py --output-dir data/outgoing_retry_actions/balanced100x5_round3_retry_gpt55_v2_selective_round4_canonical --expected-count 64` - status `ok`.
- Selective round4 metadata export - wrote 64 rows.
- `git diff --check` - passed.
- Secret scan for the provided API key outside `.env` and `data/api_logs/**` returned no matches.

Blockers:

- None.

Next recommended step:

- Commit/push `src/gen_retry/prompts/retry_replan_prompt.py` and `data/exchange/api_to_gpu/balanced100x5_round4_retry_gpt55_v2_selective_canonical/generation_metadata.jsonl`, then generate/evaluate this 64-sample selective round4 batch on the GPU machine.

## Round4 Selective Normal Teacher Plans

Status: completed.

Completed work:

- Reused the same 64 selected round3 packages as the canonical-display ablation.
- Copied the 64 source trajectories into an isolated ablation trajectory directory so the normal round4 teacher run would not overwrite canonical-display trajectory state.
- Ran normal `gpt-5.5` teacher retry with `GEN_RETRY_REPLAN_STYLE` unset over 4 shards:
  - 64/64 teacher actions
  - 0 API/package failures
  - 0 quality critical issues
- Rebuilt the normal round4 retry action manifest:
  - `data/outgoing_retry_actions/balanced100x5_round3_retry_gpt55_v2_selective_round4_normal/retry_action_manifest.jsonl`
  - 64 packages, status `ok`, 0 critical quality issues.
- Exported normal round4 GPU metadata:
  - `data/exchange/api_to_gpu/balanced100x5_round4_retry_gpt55_v2_selective_normal/generation_metadata.jsonl`
  - 64 rows, 0 missing `vqa_list`, seed, generation prompt, or previous action.

Normal style check:

- `generation_prompt_source`: `teacher_retry_replan`.
- Average retry prompt length: 196.4 words.
- Teacher action branch sources: 22 `best_so_far`, 42 `latest`.

Validation commands run:

- `python3 scripts/test.py --contains gpt-5.5` with `.env` loaded - passed.
- Isolated trajectory copy for the 64 selected packages - copied 64, missing 0.
- `python3 scripts/build_geneval2_retry_plans.py ... --teacher gpt55 --max-retry 4` over 4 selective shards with `GEN_RETRY_REPLAN_STYLE` unset - all shards status `ok`.
- `python3 scripts/rebuild_retry_action_manifest.py --output-dir data/outgoing_retry_actions/balanced100x5_round3_retry_gpt55_v2_selective_round4_normal --expected-count 64` - status `ok`.
- `python3 scripts/export_retry_generation_metadata.py --trajectories-dir data/raw_trajectories_ablation/geneval2_balanced_100x5_round0_gpt55_round4_normal64 --output data/exchange/api_to_gpu/balanced100x5_round4_retry_gpt55_v2_selective_normal/generation_metadata.jsonl --retry-round 4` - wrote 64 rows.
- Secret scan for API-key-like strings outside `.env` and `data/api_logs/**` returned no matches.

Blockers:

- None.

Next recommended step:

- Commit/push `data/exchange/api_to_gpu/balanced100x5_round4_retry_gpt55_v2_selective_normal/generation_metadata.jsonl` and `docs/RUN_COMMANDS.md`, then generate/evaluate this 64-sample normal round4 comparison batch on the GPU machine.
