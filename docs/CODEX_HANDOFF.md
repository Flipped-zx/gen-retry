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

Not implemented by instruction:

- full retry loop
- image generation
- RL
- training
- web search integration
- raw GenEval evaluator adapter

## Safety Notes

- No dependency installation commands were run.
- No writes were made outside the current `gen-retry` repository.
- `../GenEvolve`, `../Gen-Searcher`, and `../GenEval` were treated as read-only.
- No GitHub push or PR command was run.

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

`python -m pytest tests` was not run because the user restricted validation to the safe stdlib-only command list for this unattended pass.

## Blockers

None.
