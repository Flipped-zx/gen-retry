# Codex Handoff
## Latest Remaining-Prompt Initial Plan Update

- The correct "remaining prompts" scope is now canonicalized as unique GenEval2 prompts not already in `data/prompts/geneval2_balanced_100.jsonl`.
- Other `geneval2_*.jsonl` files are not mutually exclusive: 148 rows outside the balanced file contain 45 rows overlapping balanced 100 and 40 duplicate rows among themselves.
- Canonical remaining prompt file: `data/prompts/geneval2_remaining_after_balanced100.jsonl` with 63 rows and 0 overlap with balanced 100.
- Canonical remaining plan cache: `data/plans/initial/geneval2_remaining_after_balanced100_gpt55/` with 63 valid GPT teacher `initial_plan` files.
- `scripts/precompute_initial_plans.py --resume` on the canonical remaining set reports `loaded=63 skipped_valid=63 pending=0`.
- Do not use `geneval2_static_position_20_gpt55` as the canonical remaining cache; that partial cache came from an interrupted per-file run and overlaps balanced 100.
- `scripts/generate_qwen_geneval_images.py` fallback prompt-id logic now matches `scripts/precompute_initial_plans.py` for prompt files without explicit `prompt_id`.

## Latest Plan-Conditioned Generation Update

- `data/plans/initial/geneval2_balanced_100_gpt55/` currently has 100 valid GPT teacher `initial_plan` cache files for the 100-row `data/prompts/geneval2_balanced_100.jsonl` set.
- `scripts/precompute_initial_plans.py --resume` reported `loaded=100 skipped_valid=100 pending=0`; no new API calls were needed in the latest pass.
- `scripts/generate_qwen_geneval_images.py` now supports `--initial-plan-dir`. When set, it generates from `initial_plan.initial_prompt` and preserves the original Geneval2 metadata prompt.
- The generation manifest now records `original_prompt`, `generation_prompt`, and `generation_prompt_source`.
- Resume safety: if an existing output directory has metadata for a different generation prompt, the script raises an error instead of silently mixing raw-prompt and plan-prompt images.
- Use a fresh output directory for the clean 100-prompt plan-conditioned image pass, for example `data/qwen_geneval2_balanced_100_x5_initial_gpt55_images`.
- Validation passed: `python3 -m compileall scripts/generate_qwen_geneval_images.py scripts/generate_qwen_geneval_images_dcu.py`; both help commands show `--initial-plan-dir`; custom stdlib checks loaded 100 valid plans and 100 plan-conditioned generation prompts; resume guard rejected the old raw-prompt output dir before model loading.
- No real Qwen-Image generation was run locally, and no new teacher API calls were made in this latest pass.

## Latest DCU Qwen Generation Update

- `scripts/generate_qwen_geneval_images.py` now supports configurable worker visibility masking through `--visible-devices-env` and optional cleanup through `--clear-visible-envs`.
- `scripts/generate_qwen_geneval_images_dcu.py` is the DCU/ROCm entrypoint. It defaults to `HIP_VISIBLE_DEVICES` for worker masking and clears `CUDA_VISIBLE_DEVICES,ROCR_VISIBLE_DEVICES` before setting the worker mask.
- Worker processes still use `--device cuda:0`; on ROCm PyTorch this is expected because HIP devices are exposed through the CUDA API surface after `HIP_VISIBLE_DEVICES` masks the process.
- Four-card DCU command is documented in `docs/QWEN_GENEVAL_BATCH.md`. If physical cards are `1,2,3,4`, use parent `HIP_VISIBLE_DEVICES=1,2,3,4` and keep script `--gpus 0,1,2,3`.
- Validation passed: `python3 -m compileall scripts/generate_qwen_geneval_images.py scripts/generate_qwen_geneval_images_dcu.py`; `python3 scripts/generate_qwen_geneval_images_dcu.py --help`; `python3 scripts/generate_qwen_geneval_images.py --help`; HIP mask mapping check resolved logical `0,1,2,3` to physical `1,2,3,4`.
- No real Qwen-Image generation was run locally.


## Scope Completed

Stage 1, Stage 2, and the requested teacher API / SFT builder slice.

Implemented:

- repo digests for `../GenEvolve`, `../Gen-Searcher`, and `../GenEval`
- codebase map
- Python package skeleton
- diagnostic normalizer
- trajectory dataclasses and stdlib validator
- tool and skill registries
- Geneval retry skill YAML
- teacher API placeholder config
- JSON schema
- minimal diagnostic and retry examples
- README safe commands
- OpenAI-compatible teacher client interface
- strict teacher retry-action schema
- deterministic dry-run teacher mode
- teacher prompt template
- JSONL teacher action builder
- JSONL SFT trajectory builder
- SFT data building documentation
- spatial diagnostic failed constraints and repair targets
- full mocked Geneval retry episode SFT output
- five-trajectory manual quality review
- stdlib SFT quality checker
- SFT data hygiene fields and masking metadata
- assistant-only SFT exporters for Qwen chat, ShareGPT/LLaMA-Factory, and TRL conversational formats
- stdlib export quality checker
- five-sample exported examples
- SFT export format documentation
- SFT strategy document
- RL design-only roadmap
- tomorrow request files for manual 50 run, 500 scaling, SFT training planning, and RL design
- visual retry trajectory collector scaffold with mock adapters
- raw episode validation and policy-only ShareGPT SFT export
- GPT-5.5 teacher and Qwen-Image-Edit adapter skeletons

Not implemented by instruction:

- full retry loop
- image generation
- RL
- training
- web search integration
- real GenEval evaluator adapter
- real image generation or real retry judging
- real GPT-5.5 teacher API call
- real Qwen-Image-Edit API call

## Safety Notes

- No dependency installation commands were run.
- No writes were made outside the current `gen-retry` repository.
- `../GenEvolve`, `../Gen-Searcher`, and `../GenEval` were treated as read-only.
- No GitHub push or PR command was run.
- No network API, teacher API, image generator, training, or RL command was run in the latest safe unattended pass.

## Dependency Notes

No external dependency is required for the current package skeleton, mock teacher mode, or the requested safe checks.

The request document mentioned Pydantic validation. Because local rules prohibit dependency installation, the implemented validator is a strict stdlib schema validator in `src/gen_retry/teacher/schemas.py`. It enforces required keys, rejects extra keys, checks types, validates decisions and known skill names, and records a JSON Schema in `schemas/teacher_retry_action.schema.json`.

Full future functionality will likely require prepared environments for:

- OpenAI-compatible API client usage.
- Geneval evaluator dependencies (`torch`, `mmdet`, `open_clip`, `pandas`, `PIL`).
- training and RL stacks.

These were not installed or invoked locally.

## Validation Results

- `python3 scripts/safe_check.py` - passed.
- `python3 -m compileall src scripts tests` - passed.
- `python3 -m json.tool examples/geneval_diagnostic_example.json` - passed.
- `python3 -m json.tool examples/geneval_retry_example.json` - passed.

Latest teacher/SFT builder validation run:

- `python3 scripts/safe_check.py` - passed.
- `python3 -m compileall src scripts tests` - passed.
- `python3 -m json.tool examples/geneval_diagnostic_example.json` - passed.
- `python3 -m json.tool examples/geneval_retry_example.json` - passed.

Latest spatial/full-episode SFT update:

- `checks.spatial_relation=false` now creates structured `spatial_relation` failed constraints and `spatial_layout` repair targets.
- `scripts/build_sft_trajectories.py` now defaults to full mocked retry episodes and supports compact mode with `--trajectory-format compact` or `--compact`.
- `data/processed/geneval_retry_sft_5_full.jsonl` was generated from the five smoke diagnostics and existing teacher actions.
- No real image generator, real Geneval evaluator, or teacher API was called.

Latest five-trajectory quality review:

- `docs/QUALITY_REVIEW_5.md` was created.
- `scripts/check_sft_quality.py` was created and run on the five full smoke trajectories.
- Checker result: 0 critical issues, 7 warnings, exit 0.
- Manual verdict: not ready to scale to 50 until mock retry judge observations are sanitized or explicit training masking is recorded.
- Repeated warning: raw detector metadata appears in user/tool context; rows should be sanitized or downstream SFT must mask user/tool observations.
- Source warning: `data/processed/teacher_retry_actions_5.jsonl` still has stale empty spatial normalized fields in rows 1 and 3, though the SFT rows recomputed structured spatial normalization.

Latest data hygiene update:

- `data/processed/geneval_retry_sft_5_full.jsonl` was regenerated with compact SFT-facing diagnostics.
- Rows now separate `assistant_trainable_messages`, `tool_observations`, `raw_detector_outputs`, and `non_trainable_context`.
- Rows include `masking_metadata` that trains only assistant summaries, tool calls, repair prompts, retry decisions, and submit/discard decisions.
- Raw detector outputs are retained only in `raw_detector_outputs` and marked non-trainable.
- `scripts/check_sft_quality.py` now passes with 0 critical issues and 0 warnings on the five full smoke trajectories.
- Current recommendation: ready to scale to 50 trajectories.

Latest five-sample exporter update:

- `src/gen_retry/data/exporters.py` exports only `assistant_trainable_messages`.
- `scripts/export_sft.py` supports `--format qwen`, `--format sharegpt`, and `--format trl`.
- `scripts/check_export_quality.py` validates JSONL exports and checks assistant train targets for raw detector metadata, tool observations, API-key-like strings, missing tool calls, missing `query_skill`, missing repair prompt, missing retry decision content, and missing submit/discard decisions.
- Generated exports:
  - `data/processed/export_qwen_5.jsonl`
  - `data/processed/export_sharegpt_5.jsonl`
  - `data/processed/export_trl_5.jsonl`
- Documentation added:
  - `docs/SFT_EXPORT_FORMATS.md`
  - `docs/SFT_STRATEGY.md`
  - `docs/RL_ROADMAP.md`
  - `docs/requests/04_run_50_teacher_batch_manual.md`
  - `docs/requests/05_scale_to_500.md`
  - `docs/requests/06_sft_training_plan.md`
  - `docs/requests/07_rl_design_only.md`

Latest validation run:

- `python3 scripts/safe_check.py` - passed.
- `python3 -m compileall src scripts tests` - passed.
- `python3 scripts/check_sft_quality.py --sft data/processed/geneval_retry_sft_5_full.jsonl --diagnostics data/smoke/geneval_diagnostics_5.jsonl --actions data/processed/teacher_retry_actions_5.jsonl` - passed with 0 critical issues and 0 warnings.
- `python3 scripts/check_export_quality.py data/processed/export_qwen_5.jsonl data/processed/export_sharegpt_5.jsonl data/processed/export_trl_5.jsonl` - passed with 0 critical issues and 0 warnings.
- `python3 -m unittest tests.test_diagnostic_normalizer tests.test_exporters tests.test_teacher_schema tests.test_trajectory_schema` - passed.

Tomorrow manual teacher batch:

- Real teacher API calls should be run from a normal terminal, not Codex, because sandboxed Python network access was not reliable during the earlier interrupted 50-sample attempt.
- Use `docs/requests/04_run_50_teacher_batch_manual.md` for exact commands to set `GEN_RETRY_TEACHER_*`, run the first 10 rows, resume rows 11-50, build full SFT trajectories, and run quality/export checks.

Latest visual retry collector update:

- Added a stdlib-only collector scaffold for prompt -> generation -> evaluation -> teacher action -> retry -> re-evaluation episodes.
- Mock mode is runnable without API keys or external dependencies.
- New CLI commands:
  - `python3 scripts/collect_mock_episodes.py --num 5`
  - `python3 scripts/validate_episodes.py data/raw_episodes`
  - `python3 scripts/export_policy_sft.py`
- Mock collection writes:
  - `data/raw_episodes/*.json`
  - `data/images/*.png` placeholder files
  - `data/sft/retry_policy_sft_sharegpt.jsonl`
- Core modules:
  - `src/gen_retry/schemas/episode_schema.py`
  - `src/gen_retry/collectors/retry_episode_collector.py`
  - `src/gen_retry/generators/`
  - `src/gen_retry/evaluators/`
  - `src/gen_retry/teachers/`
  - `src/gen_retry/filters/`
  - `src/gen_retry/export/`
- Real adapter skeletons are present but intentionally do not run in tests:
  - `src/gen_retry/teachers/gpt55_teacher_adapter.py`
  - `src/gen_retry/generators/qwen_image_edit_adapter.py`
- Success is decided only by the evaluator. The teacher only chooses next actions.

Latest collector validation:

- `python3 scripts/collect_mock_episodes.py --num 5` - passed and saved 5 episodes.
- `python3 scripts/validate_episodes.py data/raw_episodes` - passed with 5 episodes and 0 errors.
- `python3 scripts/export_policy_sft.py` - passed and wrote 5 policy SFT rows.
- `python3 -m unittest discover tests` - passed with 19 tests.
- `python3 scripts/safe_check.py` - passed.
- `python3 -m compileall src scripts tests` - passed.

Latest Qwen-Image + Geneval batch diagnostic update:

- Added `scripts/collect_qwen_geneval_diagnostics.py` to plan or run Qwen-Image candidate generation and Geneval evaluation.
- Added `src/gen_retry/collectors/qwen_geneval_batch.py` for 4-GPU command-template orchestration.
- Added `src/gen_retry/evaluators/geneval_result_normalizer.py` to convert raw Geneval JSON into structured `NormalizedGenevalReport` and teacher-ready diagnostics.
- Added `data/prompts/geneval_pilot_10.jsonl` with 10 prompt records covering counting, color, spatial, object presence, mixed, and visibility cases.
- Added `docs/QWEN_GENEVAL_BATCH.md` with prepared-server commands.
- Plan-only validation generated `data/runs/qwen_geneval_pilot_10/generation_manifest.jsonl` with 40 candidates: 10 prompts x 4 images.
- Expected real-run outputs:
  - `candidate_diagnostics.jsonl` for full per-image diagnostics.
  - `teacher_diagnostics.jsonl` for later GPT teacher action GT construction.
- No real Qwen-Image generation, Geneval evaluation, GPT API, training, RL, or dependency installation was run locally.

Latest Qwen/Geneval validation:

- `python3 scripts/collect_qwen_geneval_diagnostics.py --prompts data/prompts/geneval_pilot_10.jsonl --output-dir data/runs/qwen_geneval_pilot_10 --images-per-prompt 4 --gpus 0,1,2,3 --plan-only` - passed and planned 40 candidates.
- `python3 -m unittest tests.test_geneval_result_normalizer tests.test_qwen_geneval_batch` - passed with 4 tests.
- `python3 -m unittest discover tests` - passed with 23 tests.
- `python3 scripts/safe_check.py` - passed.
- `python3 -m compileall src scripts tests` - passed.

`python -m pytest tests` was not run because the user restricted validation to the safe stdlib-only command list for this unattended pass.

## Blockers

- Real teacher API batch execution from inside Codex is blocked/unreliable due sandbox network restrictions. Manual normal-terminal execution is documented in `docs/requests/04_run_50_teacher_batch_manual.md`.

## Latest Relay/Reference Repo Note

- User relay base URL: `https://skyapi.duckdns.org/v1`.
- Treat Gen-Searcher and GenEvolve as reference-only material for implementation borrowing; do not manage or commit them as part of `gen-retry`.
- Prefer the compressed digests in `docs/repo_digests/` before reading reference repos directly.
- `.gitignore` now ignores local in-repo copies named `Gen-Searcher/`, `GenEvolve/`, `gen-searcher/`, and `gen-evolve/`.
- `scripts/test.py` was changed to read API keys from environment variables only; hard-coded relay key material was removed.
- Validation run: `rg -n "sk-[A-Za-z0-9_-]+" ...` found no matches; `python3 -m compileall src scripts tests` passed.

## Latest Geneval2 GPT-Teacher Smoke

- `.env` was loaded without printing API keys.
- Relay `/models` smoke succeeded and listed `gpt-5.5` and `gpt-image-2`.
- `data/prompts/geneval2_smoke_3.jsonl` was extracted from `../GenEval2/geneval2_data.jsonl`.
- `scripts/collect_mock_episodes.py` now supports `--teacher mock|gpt55|seed`.
- GPT-5.5 teacher smoke was run on 3 Geneval2 prompts with mock generator/evaluator:
  - output episodes: `data/raw_episodes/geneval2_gpt55_smoke/`
  - mock images: `data/images/geneval2_gpt55_smoke/`
  - SFT export: `data/sft/geneval2_gpt55_smoke_sharegpt.jsonl`
  - rejected rows: `data/rejected/geneval2_gpt55_smoke_rejected.jsonl`
- All 3 episodes validated with 0 errors and each uses `initial_plan,retry_replan`.
- Export produced 6 ShareGPT rows: one `initial_plan` and one `retry_replan` row per episode.
- One standalone `gpt-image-2` adapter smoke succeeded:
  - `data/images/api_smoke/gpt_image2_smoke.png`
  - `data/images/api_smoke/gpt_image2_smoke.png.json`
- First GPT teacher attempt hit relay HTTP 502 `upstream temporarily unavailable`; `GPT55TeacherAdapter` now retries 429/5xx HTTP failures according to `GEN_RETRY_TEACHER_MAX_RETRIES`.
- `data/api_logs/` is ignored by git because it stores raw teacher API responses.
- Full real GenEval2 evaluation was not run yet; official GenEval2 loads Qwen3-VL-8B and should be treated as the next heavier end-to-end step.

## Latest Real Geneval2 Closed-Loop Smoke

- User approved environment changes. Installed/changed:
  - `huggingface-hub==0.36.2` to satisfy `transformers==4.57.0`.
  - `pytest==9.1.1`.
- `scripts/collect_real_episodes.py` is now safer and closer to the requested smoke CLI:
  - default `--num 3`;
  - `--allow-all` is required for `--num 0`;
  - supports `--dry-run`;
  - supports `--generator gpt_image2`.
- Real loop was run with 3 Geneval2 prompts and `--max-retry 2`:
  - prompts: `data/prompts/geneval2_smoke_3.jsonl`
  - episodes: `data/raw_episodes_real_smoke/`
  - SFT: `data/sft/retry_sft_real_smoke.jsonl`
  - real images/evals: `data/images/episode_*.png` and `data/images/episode_*.geneval2.json`
- Real smoke metrics:
  - episodes: 3
  - images: 4
  - GenEval2 evaluations: 4
  - `initial_plan` SFT rows: 3
  - `retry_replan` SFT rows: 1
  - failures in final run: 0
- Outcomes:
  - `episode_000000_172975eb2bc3`: `pass_without_retry`
  - `episode_000001_d0db5e565544`: `passed_after_retry`
  - `episode_000002_948e80ea1b67`: `pass_without_retry`
- The retry case confirms the intended path:
  - initial plan -> GPT Image 2 -> GenEval2 failed count constraint -> GPT-5.5 `retry_replan` -> GPT Image 2 regenerate -> GenEval2 pass.
- Important fixes made during the real smoke:
  - `scripts/run_geneval2_single_image.py` now passes absolute image paths to the official evaluator subprocess.
  - `src/gen_retry/export/export_sft.py` strips image paths, raw Geneval2 rows, `raw_report`, `details.raw`, and API-log-like fields from SFT user context.
  - planner action schemas reject extra keys and direct edit field variants.
  - teacher prompts explicitly require exact JSON schema keys and regeneration-only retry.
  - image generator adapter retries 429/5xx relay failures and treats env strings `None`/`null` as unset for image options.
- Validation:
  - `python3 scripts/collect_mock_episodes.py --num 5` passed.
  - `python3 scripts/validate_episodes.py data/raw_episodes` passed with 5 episodes and 0 errors.
  - `python3 scripts/export_sft.py --input data/raw_episodes --output data/sft/retry_sft_mock_check.jsonl` exported 10 rows.
  - `python3 -m pytest tests` passed with 50 tests.
  - `python3 scripts/validate_episodes.py data/raw_episodes_real_smoke --strict-images` passed with 3 episodes and 0 errors.
  - `python3 scripts/export_sft.py --input data/raw_episodes_real_smoke --output data/sft/retry_sft_real_smoke.jsonl` exported 4 rows.
  - Custom audit found 0 direct-edit fields in assistant actions and 0 raw/image/API fields in real SFT user context.
  - `python3 scripts/safe_check.py` passed.
  - `python3 -m compileall src scripts tests` passed.
- Recommended next step: run 10 real Geneval2 prompts with `--max-retry 2`, inspect retry frequency and SFT quality, then decide whether to scale further.

## Latest Static Candidate Smoke 5

- Ran first 5 rows from `data/prompts/geneval2_static_retry_candidates_25.jsonl`.
- Output:
  - episodes: `data/raw_episodes_real_static_smoke_5/`
  - images/evals: `data/images/real_static_smoke_5/`
  - SFT: `data/sft/retry_sft_real_static_smoke_5.jsonl`
  - rejected: `data/rejected/retry_replan_real_static_smoke_5_rejected.jsonl`
- Metrics:
  - episodes: 5
  - images: 5
  - Geneval2 evaluations: 5
  - outcomes: 5 `pass_without_retry`
  - retry triggers: 0
  - `initial_plan` SFT rows: 5
  - `retry_replan` SFT rows: 0
- All 5 were medium static prompts with one spatial relation and atom_count 4. They were too easy for `gpt-image-2`.
- Validation:
  - `python3 scripts/validate_episodes.py data/raw_episodes_real_static_smoke_5 --strict-images` passed with 5 episodes and 0 errors.
  - SFT export produced 5 rows.
  - Custom audit found 0 raw/image/API fields in SFT user context and 0 direct-edit fields.
- Conclusion: do not spend more API budget on the medium bucket for retry mining. Next run should target `data/prompts/geneval2_static_hard_30.jsonl`, especially large-count/count+position prompts, before trying very-hard verb prompts.

## Latest Atom Threshold + Tool Trajectory Export

- Geneval2 diagnostic atom threshold is now configurable in:
  - `src/gen_retry/evaluators/geneval2_result_normalizer.py`
  - `src/gen_retry/evaluators/geneval2_adapter.py`
  - `scripts/collect_real_episodes.py --atom-threshold`
  - `scripts/normalize_geneval2_results.py --atom-threshold`
- Current default remains `0.5` for backward compatibility.
- The threshold is documented in raw reports as training-time diagnostic normalization only; it is not a replacement for official GenEval2 benchmark scoring.
- Compact SFT export is preserved.
- `scripts/export_sft.py --format tool` now writes full episode tool trajectories.
- `scripts/export_sft.py --format both` writes compact rows plus tool trajectories.
- Allowed trajectory tools are only `query_skill`, `generate_image`, and `judge_image`.
- Tool responses are marked non-trainable with metadata:
  - `trainable_message_indices`
  - `non_trainable_message_indices`
  - `tool_responses_trainable: false`
- Fixed skill guidance lives in `src/gen_retry/skills/skill_library.py`.
- Tool trajectory validation lives in `scripts/validate_tool_sft.py`.
- Geneval2 threshold audit lives in `scripts/audit_geneval2_thresholds.py`.

Validation completed:

- `python3 scripts/collect_mock_episodes.py --num 5` passed.
- `python3 scripts/validate_episodes.py data/raw_episodes` passed with 5 episodes and 0 errors.
- `python3 scripts/export_sft.py --input data/raw_episodes --output data/sft/retry_sft_mock_compact.jsonl --format compact` exported 10 rows.
- `python3 scripts/export_sft.py --input data/raw_episodes --output data/sft/retry_sft_mock_tool.jsonl --format tool` exported 5 rows.
- `python3 scripts/export_sft.py --input data/raw_episodes --output data/sft/retry_sft_mock_both_compact.jsonl --tool-output data/sft/retry_sft_mock_both_tool.jsonl --format both` passed.
- `python3 scripts/validate_tool_sft.py data/sft/retry_sft_mock_tool.jsonl` passed.
- `python3 scripts/validate_tool_sft.py data/sft/retry_sft_mock_both_tool.jsonl` passed.
- `python3 scripts/audit_geneval2_thresholds.py --input data/raw_episodes --thresholds 0.5,0.9,0.95 --output data/analysis/geneval2_threshold_audit_mock.json` passed.
- `python3 -m compileall src scripts tests` passed.
- `python3 -m pytest` passed with 53 tests.

Real Geneval2 atom-0.90 smoke:

- Command used exactly 3 prompts from `data/prompts/geneval2_smoke_3.jsonl`.
- Settings:
  - `--teacher gpt55`
  - `--generator gpt_image2`
  - `--evaluator geneval2`
  - `--max-retry 2`
  - `--pass-threshold 0.95`
  - `--atom-threshold 0.90`
- Outputs:
  - episodes: `data/raw_episodes_real_smoke_atom090/`
  - images/evals: `data/images/real_smoke_atom090/`
  - compact SFT: `data/sft/retry_sft_real_smoke_atom090_compact.jsonl`
  - tool SFT: `data/sft/retry_sft_real_smoke_atom090_tool.jsonl`
  - threshold audit: `data/analysis/geneval2_threshold_audit_real_atom090.json`
- Metrics:
  - episodes: 3
  - generated images: 3
  - Geneval2 evaluations: 3
  - retry replans: 0
  - outcomes: 3 `pass_without_retry`
  - failure type distribution under atom threshold 0.90: `{}`
  - retry trigger rate: 0.0
- Validation:
  - `python3 scripts/validate_episodes.py data/raw_episodes_real_smoke_atom090` passed.
  - real compact/tool exports each produced 3 rows.
  - `python3 scripts/validate_tool_sft.py data/sft/retry_sft_real_smoke_atom090_tool.jsonl` passed.
  - real threshold audit passed.

Current read:

- Explicit trajectory export is directionally right for this project. It matches the controller-training pattern: assistant learns planning, tool calls, verifier reading, retry diagnosis, retry prompt construction, and rule-based submit/stop.
- This does not conflict with coding-agent style trajectories as long as tool outputs stay non-trainable and the available tools remain fixed and narrow.
- The current 3-prompt atom-0.90 smoke is ready as a functional smoke, but not enough as retry SFT data because it contains no retry cases.
- For retry mining, use harder prompts next, preferably a capped 5-10 row run from `data/prompts/geneval2_static_hard_30.jsonl`.

## Latest Hard Atom-0.90 Retry-Mining Checkpoint

- Ran the first 5 prompts from `data/prompts/geneval2_static_hard_30.jsonl`.
- Settings:
  - `--teacher gpt55`
  - `--generator gpt_image2`
  - `--evaluator geneval2`
  - `--max-retry 2`
  - `--pass-threshold 0.95`
  - `--atom-threshold 0.90`
- Outputs:
  - episodes: `data/raw_episodes_real_hard_smoke_atom090_5/`
  - images/evals: `data/images/real_hard_smoke_atom090_5/`
  - compact SFT: `data/sft/retry_sft_real_hard_atom090_5_compact.jsonl`
  - tool SFT: `data/sft/retry_sft_real_hard_atom090_5_tool.jsonl`
  - threshold audit: `data/analysis/geneval2_threshold_audit_real_hard_atom090_5.json`
- Metrics:
  - episodes: 5
  - attempts / generated images / Geneval2 evals: 7
  - episode retry rate: 1/5
  - retry replan actions: 2
  - outcomes: 4 `pass_without_retry`, 1 `regressed`
  - compact export rows: 5 initial-plan rows
  - compact retry rows: 0 because regressed retry actions are filtered
  - tool trajectory rows: 5
  - tool trajectory retry rows: 1 regressed full trajectory
  - atom thresholds seen in raw reports: `0.9`
  - failure types across attempts: `count_mismatch: 2`, `spatial_mismatch: 1`
- Important episode:
  - `data/raw_episodes_real_hard_smoke_atom090_5/episode_000003_df8642f2e8bb.json`
  - prompt: `seven backpacks on top of three sparkling flamingos`
  - attempt 0 score `0.96218`, failed backpack `count_mismatch`
  - retry 1 score `0.83332`, still failed count
  - retry 2 score `0.85285`, failed spatial relation; final outcome `regressed`
- Validation:
  - `python3 scripts/validate_episodes.py data/raw_episodes_real_hard_smoke_atom090_5` passed.
  - compact/tool exports passed.
  - `python3 scripts/validate_tool_sft.py data/sft/retry_sft_real_hard_atom090_5_tool.jsonl` passed.
  - threshold audit passed.
  - `python3 -m pytest` passed with 53 tests.
- Implementation note:
  - `scripts/audit_geneval2_thresholds.py` was fixed so raw episode directories are audited by `episode_id:attempt_round`, not merged by the original GenEval2 prompt text.

Current data-quality read:

- This checkpoint is useful for retry mining and RL-style negative-feedback analysis.
- It is not sufficient as positive retry SFT because the only retry episode regressed.
- Compact export currently does the safer thing by rejecting regressed retry actions.
- Tool trajectory rows are structurally valid, but downstream training should filter out `final_outcome=regressed` rows or mask those retry spans unless intentionally training negative/stop behavior.
- A 20-prompt hard run is reasonable as a mining run, but not as a guaranteed final SFT run. The acceptance target for SFT should be counts of accepted positive retry actions, not just number of prompts executed.

## Latest Hard Atom-0.90 Next20 Mining Run

- Resumed the interrupted run from 13 completed episodes and finished all 20 rows from `data/prompts/geneval2_static_hard_next20.jsonl`.
- Settings:
  - `--teacher gpt55`
  - `--generator gpt_image2`
  - `--evaluator geneval2`
  - `--max-retry 2`
  - `--pass-threshold 0.95`
  - `--atom-threshold 0.90`
- Outputs:
  - episodes: `data/raw_episodes_real_hard_atom090_next20/`
  - images/evals: `data/images/real_hard_atom090_next20/`
  - compact SFT: `data/sft/retry_sft_real_hard_atom090_next20_compact.jsonl`
  - tool SFT: `data/sft/retry_sft_real_hard_atom090_next20_tool.jsonl`
  - rejected retry rows: `data/rejected/retry_replan_real_hard_atom090_next20_rejected.jsonl`
  - threshold audit: `data/analysis/geneval2_threshold_audit_real_hard_atom090_next20.json`
- Metrics:
  - episodes: 20
  - attempts / generated images / GenEval2 evals: 27
  - episodes with retry: 5/20
  - retry attempts: 7
  - outcomes: 15 `pass_without_retry`, 3 `passed_after_retry`, 2 `regressed`
  - compact SFT rows: 23 total = 20 `initial_plan` + 3 positive `retry_replan`
  - rejected retry rows: 4 regressed retry spans
  - tool trajectory rows: 20, including 2 regressed trajectories for analysis/RL-style feedback
  - failure types across attempts at atom threshold 0.90: `count_mismatch: 9`, `relation_mismatch: 3`
  - first-attempt failure types: `count_mismatch: 6`, `relation_mismatch: 1`
- Positive retry SFT episodes:
  - `episode_000003_d2ea02c7b4ab`: `five pink motorcycles and seven wooden raccoons`
  - `episode_000004_d337a72bf9f9`: `a brown flamingo and six cows and seven penguins`
  - `episode_000005_7a2c81f0956c`: `five plastic mushrooms and seven spotted trucks`
- Regressed analysis episodes:
  - `episode_000013_0a241b6fa964`: `four trumpets and two brown trucks and four toys`
  - `episode_000019_c2572ed5e9de`: `seven penguins jumping over three kangaroos`
- Validation:
  - `python3 scripts/validate_episodes.py data/raw_episodes_real_hard_atom090_next20 --strict-images` passed with 20 episodes and 0 errors.
  - `python3 scripts/export_sft.py --input data/raw_episodes_real_hard_atom090_next20 --output data/sft/retry_sft_real_hard_atom090_next20_compact.jsonl --tool-output data/sft/retry_sft_real_hard_atom090_next20_tool.jsonl --rejected-output data/rejected/retry_replan_real_hard_atom090_next20_rejected.jsonl --format both` passed.
  - `python3 scripts/validate_tool_sft.py data/sft/retry_sft_real_hard_atom090_next20_tool.jsonl` passed with 20 rows and 0 errors.
  - `python3 scripts/audit_geneval2_thresholds.py --input data/raw_episodes_real_hard_atom090_next20 --thresholds 0.5,0.9,0.95 --output data/analysis/geneval2_threshold_audit_real_hard_atom090_next20.json` passed.
  - `python3 scripts/safe_check.py` passed.
  - `python3 -m compileall src scripts tests` passed.
  - `python3 -m pytest` passed with 53 tests.
  - Secret-pattern scan over non-secret repo inputs found no `sk-*` matches.
  - Manual spot-check of the 3 positive compact retry rows passed: all use `decision=regenerate`, no mask/bounding-box/inpainting/source-image/direct-edit fields, and all repair `count_mismatch` through stronger exact-count, visibility, separation, non-overlap, and negative constraints.

Current data-quality read:

- This run produced 3 accepted positive retry-replan SFT samples, so it is the first useful small positive retry mining set.
- Compact export is correctly excluding the 4 retry spans from the 2 regressed episodes.
- Keep the regressed tool trajectories for analysis/RL or negative-feedback design, but do not include them in ordinary positive SFT without masking/filtering.
- Next practical step is manual inspection of the 3 positive retry compact rows before spending more API budget on another hard/verb-biased mining batch.

## Latest Offline Manual-Transfer Planner

- Reviewed the pasted goal at `/root/.codex/attachments/b026acba-2866-49c0-b1bf-2987362198e0/pasted-text-1.txt`.
- Implemented an offline JSON-only GenEval2 evaluation-to-`retry_replan` flow for manual cross-machine transfer.
- New CLI:
  - `python3 scripts/offline_evaluate_and_plan.py --input data/incoming_generation_results/*.json --output-dir data/outgoing_retry_actions --max-retry 3 --teacher gpt55 --evaluator geneval2`
  - `python3 scripts/validate_offline_retry_package.py <input-or-output-or-trajectory.json>`
- New core module:
  - `src/gen_retry/offline_planner.py`
- New Chinese report:
  - `docs/OFFLINE_GENEVAL2_RETRY_PIPELINE.md`
- Teacher retry action now carries:
  - `branch_source`
  - `branch_source_round`
- Teacher retry input context now carries:
  - full `previous_action`
  - `current_round`
  - `current_eval_report`
  - explicit `best_so_far`
  - fixed, persistent, new, and regressed constraints
  - score deltas from previous and best
  - available skills
- Raw offline trajectories are candidate-level and record generation, previous action, normalized evaluation, next planner action, transition diffs, and best-so-far memory.
- Stop logic is code-side, not learned by the model:
  - `passed`
  - `max_retry`
  - `no_improvement`
  - `large_regression`
  - `invalid_teacher_action`
- Compact SFT retry export now includes the memory fields required for step-level `retry_replan` learning while keeping local `image_path` out of the SFT user context.
- Validation run:
  - `python3 -m compileall src scripts tests` passed.
  - `python3 -m unittest tests.test_actions tests.test_offline_planner tests.test_export_sft` passed with 10 tests.
  - `python3 -m unittest tests.test_actions tests.test_offline_planner` passed with 7 tests after the new test temp directory was moved inside the repo.
  - `python3 -m json.tool schemas/teacher_retry_action.schema.json >/dev/null` passed.
  - `python3 scripts/safe_check.py` passed.
  - `git diff --check -- <offline planner touched files>` passed.
- No dependency installation, training, RL, image generation, RPC, file sync, GitHub push, or sibling-repo writes were performed.

Next practical step:

- Create or copy one real Machine A generation package into `data/incoming_generation_results/`, run the offline planner with `--teacher mock` first, validate all JSON outputs, then rerun with `--teacher gpt55` after `GEN_RETRY_TEACHER_*` is set.

## Active Qwen-Image 100 x 5 Generation Run

User priority:

- Review the real objective and start image generation first.
- Extract 100 prompts.
- Generate 4-5 images per prompt; this checkpoint uses 5 images, so 500 total.
- Show total progress and ETA so the run is not opaque.

Files added or patched in this checkpoint:

- `scripts/select_balanced_geneval2_prompts.py`
- `scripts/precompute_initial_plans.py`
- `scripts/run_geneval2_batch.py`
- `scripts/validate_geneval2_pilot_state.py`
- `src/gen_retry/utils/progress.py`
- `scripts/generate_qwen_geneval_images.py`
- `scripts/collect_qwen_geneval_diagnostics.py`
- `src/gen_retry/collectors/qwen_geneval_batch.py`
- `docs/GENEVAL2_QWEN_PILOT_100_REPORT.md`
- `data/prompts/geneval2_balanced_100.jsonl`
- `data/prompts/geneval2_balanced_100.summary.json`
- `data/prompts/geneval2_balanced_100.summary.md`
- `data/qwen_geneval2_balanced_100_x5_manifest/generation_manifest.jsonl`

Current active run:

- Started with `setsid`, because ordinary background/nohup children were cleaned up by the execution wrapper.
- PID file: `data/run_logs/qwen_geneval2_balanced_100_x5.pid`
- Log: `data/run_logs/qwen_geneval2_balanced_100_x5.log`
- Output dir: `data/qwen_geneval2_balanced_100_x5_images/`
- Parent PID observed: `1036`
- Child worker PID observed: `1042`
- Checkpoint progress observed: `13/500`
- Early shard ETA observed: about `10:35:29`

Monitor the active run:

```bash
tail -f data/run_logs/qwen_geneval2_balanced_100_x5.log
find data/qwen_geneval2_balanced_100_x5_images -path '*/samples/*.png' -type f | wc -l
ps -p "$(cat data/run_logs/qwen_geneval2_balanced_100_x5.pid)" -o pid=,ppid=,stat=,etime=,cmd=
nvidia-smi
```

Resume command if interrupted:

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
  --resume \
  --skip-grid \
  --progress-interval 60
```

Validation already run:

- Prompt selection wrote 100 rows.
- Plan-only manifest wrote 500 rows.
- `python3 -m compileall src scripts tests` passed.
- Stdlib JSONL row checks passed for prompt file and manifest.
- `git diff --check` passed for the touched source files.
- One real Qwen smoke image completed successfully before starting the full run.
- `scripts/precompute_initial_plans.py` was dry-run tested with `--teacher mock`; wrote 100 valid plan caches under `data/plans/initial_mock_balanced_100/`.
- `scripts/run_geneval2_batch.py` was smoke-tested with `--allow-partial --plan-only`; while generation was still running it saw 7 existing image jobs and 493 missing images, and did not start GenEval2.
- `scripts/validate_geneval2_pilot_state.py` was tested in partial mode; it wrote `data/analysis/geneval2_qwen_pilot_state_partial.json` with 13 existing images, 487 missing images, 100 valid mock initial plans, and 0 errors.

Important caveats:

- The full generation run is still active. Do not mark the overall goal complete until the 500 images are finished and verified.
- Parent total ETA is initially pessimistic because it includes model loading time. The shard-level progress lines are a better early ETA.
- No GenEval2 evaluation, retry planning, or SFT export has been run yet for this 100-prompt pilot.
- Directly running `../GenEval2/evaluation.py --help` is unsafe/noisy because that script loads Qwen before argparse and may try remote model resolution. Use `scripts/run_geneval2_batch.py`, which patches the evaluation copy to the local `--qwen3vl-model-path`.

Run teacher initial-plan precompute in the API environment:

```bash
python3 scripts/precompute_initial_plans.py \
  --prompts data/prompts/geneval2_balanced_100.jsonl \
  --output-dir data/plans/initial/geneval2_balanced_100_gpt55 \
  --teacher gpt55 \
  --num-workers 4 \
  --resume
```

Run GenEval2 after all 500 images exist:

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

Check current pilot state without starting GPU work:

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

## Latest Geneval2 Balanced 100 GPT Teacher Initial Plans

Completed the real teacher initial-plan API pass for the 100 balanced Geneval2 prompts.

Inputs and outputs:

- Prompts: `data/prompts/geneval2_balanced_100.jsonl`
- Real teacher plan cache: `data/plans/initial/geneval2_balanced_100_gpt55/`
- Valid plan files: 100 JSON files in the parent plan directory.
- Historical failed logs: `data/plans/initial/geneval2_balanced_100_gpt55/_errors/` still contains older failed-attempt records from missing env / DNS failures. These were not deleted. Treat the parent directory JSON files as the current successful cache.

API run details:

- Loaded local `.env` without printing API keys.
- Relay `/models` smoke succeeded and target model `gpt-5.5` was present.
- 1-row initial-plan smoke succeeded.
- Full resumed run skipped the existing smoke row and completed the remaining 99 rows.
- Final API batch result: `ok=99 errors=0`, giving 100 total valid cached plans.

Validation run:

- `find data/plans/initial/geneval2_balanced_100_gpt55 -maxdepth 1 -type f -name '*.json' | wc -l` returned 100.
- Custom stdlib schema audit loaded all 100 prompt rows, matched every `prompt_id` to a plan file, parsed every `initial_plan` with `InitialPlanAction`, and found 0 missing / 0 invalid / 0 prompt mismatches.
- `python3 -m compileall src scripts tests` passed.

Next practical step:

- For the 100-prompt pilot, switch any pilot validation or downstream orchestration from `data/plans/initial_mock_balanced_100/` to `data/plans/initial/geneval2_balanced_100_gpt55/`.
- After all 500 initial Qwen images exist, run GenEval2 evaluation and then use these real initial plans as context for retry planning.

## Latest GenEval2 Retry SFT Goal Outline

Created a concise persistent workflow outline:

- `docs/GENEVAL2_RETRY_SFT_GOAL.md`

Purpose:

- Keep the project aligned on the intended data construction flow:
  `original prompt -> teacher initial_plan -> generation -> GenEval2 diagnosis -> teacher retry_replan -> retry generation -> re-evaluation -> accepted or rejected trajectory`.
- Make explicit that this is verifier-guided repair training, not generic prompt rewriting.
- Make explicit that the earlier 20-prompt hard mining run is the quality floor: new accepted SFT trajectories must be at least as good as those high-quality examples, and low-quality or regressed retries should be filtered/rejected rather than included for volume.

Gen-Searcher reference finding:

- Relevant service: `Gen-Searcher/qwen_image_api_server/qwen-image-edit/api.py`.
- It uses `QwenImageEditPlusPipeline`, so it is an image-edit service rather than the current Qwen-Image-2512 text-to-image batch script.
- Useful operational defaults from that service:
  - `num_inference_steps=40`
  - `true_cfg_scale=4.0`
  - `guidance_scale=1.0`
  - `negative_prompt=" "`
  - `num_images_per_prompt=1`
  - one loaded pipeline per GPU with per-GPU lock scheduling and timeout/reload recovery
- RL reward workflow calls the Qwen Edit service with up to 3 reference images.

Current gen-retry pilot recommendation:

- Keep using `scripts/generate_qwen_geneval_images.py` for local Qwen-Image-2512 text-to-image generation.
- Current local defaults remain:
  - `steps=50`
  - `true_cfg_scale=4.0`
  - `width=1664`
  - `height=928`
  - `negative_prompt=" "`
  - `positive_suffix=""`
- Plan-conditioned initial generation is now implemented. Use `--initial-plan-dir data/plans/initial/geneval2_balanced_100_gpt55` and a fresh output directory so generation uses cached `initial_plan.initial_prompt` while original GenEval2 metadata is preserved for evaluation.

## Latest Qwen Generation Suffix And Image Ignore Update

- `scripts/generate_qwen_geneval_images.py --positive-suffix` now defaults to an empty string.
- Recommended Qwen generation commands no longer append `Ultra HD, 4K, cinematic composition.`.
- Rationale: GenEval2 cares about count/object/attribute/relation/visibility constraints; a generic style suffix can encourage aesthetic composition at the cost of countability and relation clarity.
- `.gitignore` now ignores generated image files under `data/`:
  - `data/**/*.png`
  - `data/**/*.jpg`
  - `data/**/*.jpeg`
  - `data/**/*.webp`
  - `data/**/*.gif`
  - `data/**/*.bmp`
  - `data/**/*.tif`
  - `data/**/*.tiff`
- Previously tracked `data/**/*.png` files were removed from the Git index with `git rm --cached`; local files remain on disk.
- Validation:
  - `python3 -m compileall scripts/generate_qwen_geneval_images.py` passed.
  - `python3 scripts/generate_qwen_geneval_images.py --help` passed.
  - `git check-ignore -v --no-index ...png` matched the new `.gitignore` rules.
  - `git ls-files 'data/**/*.png' 'data/**/*.jpg' 'data/**/*.jpeg' 'data/**/*.webp' 'data/**/*.gif' | wc -l` returned 0.
