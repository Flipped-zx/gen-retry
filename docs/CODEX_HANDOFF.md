# Codex Handoff

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

Not implemented by instruction:

- full retry loop
- image generation
- RL
- training
- web search integration
- raw GenEval evaluator adapter
- real image generation or real retry judging

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

`python -m pytest tests` was not run because the user restricted validation to the safe stdlib-only command list for this unattended pass.

## Blockers

- Real teacher API batch execution from inside Codex is blocked/unreliable due sandbox network restrictions. Manual normal-terminal execution is documented in `docs/requests/04_run_50_teacher_batch_manual.md`.
