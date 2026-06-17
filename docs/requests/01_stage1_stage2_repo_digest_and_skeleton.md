# Task: Stage 1 + Stage 2 for Gen-Retry

Read `docs/requests/00_project_brief.md` first.

Only complete Stage 1 and Stage 2. Do not implement full training, OpenAI teacher generation, or full retry episodes yet.

## Stage 1: Repository Digests

Inspect the source code of:

- ../GenEvolve
- ../Gen-Searcher
- ../GenEval

Create:

- docs/repo_digests/genevolve_digest.md
- docs/repo_digests/gen_searcher_digest.md
- docs/repo_digests/geneval_digest.md
- docs/CODEBASE_MAP.md

The digests must be actionable engineering notes from source code, not only paper summaries.

For GenEvolve, extract:
- repository tree and key files
- trajectory format
- tool protocol
- query_knowledge / skill mechanism
- prompt-reference program format
- SFT data format
- training script structure
- filtering logic

For Gen-Searcher, extract:
- repository tree and key files
- search / image_search / browse tool format
- trajectory data format
- SFT data construction
- RL data construction
- final grounded prompt format
- tool observation handling

For GenEval, extract:
- repository tree and key files
- prompt categories
- evaluator interface
- intermediate detection outputs
- object/count/color/spatial checks
- pass/fail aggregation
- how to access per-prompt diagnostics

## Stage 2: Gen-Retry Skeleton

Create a clean Python package structure:

- README.md
- pyproject.toml
- configs/skills/geneval_skills.yaml
- configs/teacher/teacher_api.example.yaml
- .env.example
- schemas/sft_trajectory.schema.json
- examples/geneval_diagnostic_example.json
- examples/geneval_retry_example.json
- src/gen_retry/__init__.py
- src/gen_retry/data/trajectory.py
- src/gen_retry/data/validate_trajectory.py
- src/gen_retry/eval/diagnostic_normalizer.py
- src/gen_retry/tools/registry.py
- src/gen_retry/tools/skills.py
- tests/test_diagnostic_normalizer.py
- tests/test_trajectory_schema.py

The first version should support a minimal example:

Input:
A Geneval-style diagnostic JSON like:
{
  "prompt": "three red apples on a blue plate",
  "category": "counting_color",
  "expected": {
    "objects": ["apple", "plate"],
    "count": {"apple": 3},
    "color": {"apple": "red", "plate": "blue"}
  },
  "detected": [
    {"label": "apple", "bbox": [123,162,205,245], "score": 0.91, "color": "red"},
    {"label": "apple", "bbox": [221,158,304,242], "score": 0.88, "color": "red"},
    {"label": "plate", "bbox": [95,210,340,295], "score": 0.76, "color": "blue"}
  ],
  "checks": {
    "object_presence": true,
    "counting": false,
    "color_binding": true
  },
  "failure_reason": "expected 3 apples, detected 2"
}

Output:
A normalized diagnostic with:
- passed_constraints
- failed_constraints
- failure_types
- preserve_candidates
- repair_targets

Also create a minimal SFT trajectory example showing:
prompt
→ parse constraints
→ first generation
→ judge diagnostic
→ call quantity_counting skill
→ preserve red apples and blue plate
→ repair count to exactly three apples
→ retry
→ judge again
→ submit

## Teacher API placeholder

Create `.env.example` and `configs/teacher/teacher_api.example.yaml` with placeholders:

GEN_RETRY_TEACHER_BASE_URL=https://your-proxy.example.com/v1
GEN_RETRY_TEACHER_API_KEY=your_api_key_here
GEN_RETRY_TEACHER_MODEL=gpt-5.5
GEN_RETRY_TEACHER_TIMEOUT=120
GEN_RETRY_TEACHER_MAX_RETRIES=3

Do not use real API keys.

## Progress / handoff

Keep a running progress log:

- docs/PROGRESS.md
- docs/CODEX_HANDOFF.md

Every time you finish a major step, update these files.

## Validation

Run lightweight tests if possible:

- python -m pytest tests
- python -m src.gen_retry.data.validate_trajectory examples/geneval_retry_example.json

If something fails, fix it or document the blocker in docs/CODEX_HANDOFF.md.

## Stop condition

Stop after:
1. repo digests are written
2. skeleton files are created
3. minimal examples exist
4. basic tests pass or blockers are documented
5. README contains exact commands
6. final repo tree is shown
