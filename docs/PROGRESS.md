# Progress

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
