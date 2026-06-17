# Gen-Retry Project Brief

We are building a new repository named `gen-retry`.

The target student model is Qwen3-VL-4B-Instruct.

The goal is to build a diagnostic-conditioned retry framework for agentic image generation.

Core idea:

original prompt
→ first generation
→ Geneval-style structured diagnostic feedback
→ identify failed constraints
→ call appropriate skill/tool
→ preserve already-correct constraints
→ repair prompt or trajectory
→ retry generation
→ re-evaluate
→ submit improved result
→ construct SFT trajectories

This is not a generic prompt rewriting project.

The learning target is:

structured diagnostic feedback
→ failure-type identification
→ skill/tool routing
→ preserve/repair separation
→ targeted retry
→ re-evaluation
→ SFT trajectory construction

Local source repositories are located one directory above this repository:

- ../GenEvolve
- ../Gen-Searcher
- ../GenEval

We should inspect these repositories once, extract reusable engineering patterns, and write persistent digests so future development does not need to re-read the full repositories every time.

Important source inspirations:

From GenEvolve:
- tool-orchestrated visual trajectories
- query_knowledge / skill mechanism
- prompt-reference program
- SFT cold start
- visual feedback and filtering logic

From Gen-Searcher:
- search / image_search / browse tool trajectories
- grounded prompt construction
- SFT trajectory format
- tool observation handling

From GenEval:
- prompt categories
- evaluator interface
- object / count / color / spatial checks
- intermediate diagnostic outputs
- per-prompt failure reasons

First focus on Geneval-Retry. Do not implement web search in the first version.

Initial tools:
- parse_constraints
- generate_image
- judge_image
- query_skill
- repair_prompt
- select_best_candidate
- submit

Initial skills:
- quantity_counting
- attribute_binding
- spatial_layout
- object_presence
- object_separation
- visibility_and_anti_occlusion
- preserve_correct_constraints

Teacher trajectory generation should use an OpenAI-compatible API client with configurable environment variables. Do not hard-code API keys.

Environment variables:
- GEN_RETRY_TEACHER_BASE_URL
- GEN_RETRY_TEACHER_API_KEY
- GEN_RETRY_TEACHER_MODEL
- GEN_RETRY_TEACHER_TIMEOUT
- GEN_RETRY_TEACHER_MAX_RETRIES

The code should support a proxy / relay API by passing a custom base_url.
