# AGENTS.md — Gen-Retry Local Development Rules

You are working on the `gen-retry` repository.

This repository is being developed on the user's local macOS machine. The user does not want you to install or modify the local Python environment.

## Absolute Safety Rules

1. Only write files inside the current `gen-retry` repository.
2. Treat the following sibling repositories as read-only:
   - ../GenEvolve
   - ../Gen-Searcher
   - ../GenEval
3. Never modify, delete, move, format, install into, or commit inside:
   - ../GenEvolve
   - ../Gen-Searcher
   - ../GenEval
4. Never run destructive commands:
   - rm -rf
   - git reset --hard
   - git clean -fd
   - chmod -R
   - chown -R
   - sudo
5. Never push to GitHub or create a PR unless the user explicitly confirms.

## Environment / Installation Rules

The user is on macOS and does not want environment changes.

Do NOT run:
- pip install
- pip3 install
- python -m pip install
- conda install
- mamba install
- poetry install
- uv pip install
- uv sync
- brew install
- npm install
- pnpm install
- yarn install

Do NOT create or modify global environments.

Do NOT install packages globally or locally.

If a dependency is missing, do not install it. Instead:
1. write the intended dependency in `pyproject.toml` or `requirements.txt`;
2. document the missing dependency in `docs/CODEX_HANDOFF.md`;
3. provide the exact command the user can run later on a server or controlled environment.

## Allowed Commands

You may run read-only or safe commands such as:

- pwd
- ls
- find
- rg
- grep
- cat
- sed
- head
- tail
- git status
- git diff
- git log
- python3 -m compileall src scripts tests
- python3 -m json.tool <some_file.json>

You may create and edit files inside the current `gen-retry` repository.

You may run lightweight validation only if it does not require installing packages.

## Testing Rules

Prefer stdlib-only checks on this local machine:

- python3 -m compileall src scripts tests
- python3 -m json.tool examples/*.json
- python3 scripts/validate_example.py if it only uses the standard library

Do not run pytest if pytest is not already installed.

If pytest or pydantic is missing, do not install it. Instead, write tests and document that full tests should be run later in a prepared environment.

## Project Goal

Build a diagnostic-conditioned retry framework for agentic image generation.

The target student model is Qwen3-VL-4B-Instruct.

The SFT data should teach the model:

Geneval diagnostic feedback
→ identify failed constraints
→ call appropriate skill/tool
→ preserve already-correct constraints
→ repair prompt or trajectory
→ retry generation
→ re-evaluate
→ submit improved result

This is not a generic prompt rewriting project.

## Current Stage

First implement Stage 1 and Stage 2 only:

Stage 1:
- Inspect ../GenEvolve, ../Gen-Searcher, and ../GenEval as read-only sources.
- Write persistent repo digests.

Stage 2:
- Create the initial `gen-retry` repository skeleton.
- Add schemas, examples, skill configs, docs, and safe validation scripts.

Do not implement full training, RL, or expensive image generation yet.

## Persistent Notes

Keep these files updated:

- docs/PROGRESS.md
- docs/CODEX_HANDOFF.md

After each major checkpoint, record:
- completed work
- changed files
- validation commands run
- blockers
- next recommended step

## Teacher API Placeholder

The teacher trajectory generation code should support an OpenAI-compatible relay/proxy API through environment variables:

- GEN_RETRY_TEACHER_BASE_URL
- GEN_RETRY_TEACHER_API_KEY
- GEN_RETRY_TEACHER_MODEL
- GEN_RETRY_TEACHER_TIMEOUT
- GEN_RETRY_TEACHER_MAX_RETRIES

Never hard-code API keys.
