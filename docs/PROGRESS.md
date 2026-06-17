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
