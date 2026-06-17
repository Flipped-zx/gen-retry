# GenEvolve Digest

Source inspected read-only from `../GenEvolve`.

## Key Tree

```text
../GenEvolve/
  README.md
  setup.py
  requirements.txt
  genevolve/
    agent.py
    generator.py
    knowledge_tool.py
    system_prompt.py
    tools/web_search.py
    knowledge/skills/*.md
  scripts/
    run_agent.py
    generate_images.py
    evaluate_images.py
    serve_vllm.sh
  examples/
    quickstart.py
    example_prompts.jsonl
```

## Runtime Trajectory Format

`genevolve/agent.py` implements a ReAct-style `GenEvolveAgent`. A rollout is stored as chat `messages`:

- initial `system` message from `SYSTEM_PROMPT`
- `user` prompt
- repeated assistant messages containing `<think>...</think>` plus either one `<tool_call>{...}</tool_call>` or `<answer>{...}</answer>`
- tool observations appended as `user` messages wrapped in `<tool_response>...</tool_response>`

The result object returned by `GenEvolveResult.to_dict()` contains:

- `prompt`
- `gen_prompt`
- `reference_images`
- `messages`
- `termination`
- `rounds`
- `error`

`ImageIdManager` allocates per-trajectory `IMG_###` identifiers and maps each identifier back to `title`, `url`, `local_path`, and `page_url`.

## Tool Protocol

The public runtime exposes exactly three tools in `system_prompt.py`:

- `search`
  - arguments: `{"queries": ["..."], "top_k": 5}`
  - implementation: `WebTextSearchTool` in `genevolve/tools/web_search.py`
  - output: markdown-like blocks with title, URL, and snippet.
- `image_search`
  - arguments: `{"query": "...", "top_k": 5}`
  - implementation: `ImageSearchTool`
  - output to agent: `--- image search result for [query] ---` followed by `IMG_###`, title, URL, local path, and page URL.
  - local behavior: downloads images to `IMAGE_DOWNLOAD_DIR` or `/tmp/genevolve_images`; drops entries without a usable local path.
- `query_knowledge`
  - arguments: `{"skill_name": "..."}`
  - implementation: `KnowledgeTool`
  - output: markdown skill guidance from `genevolve/knowledge/skills/<skill>.md`.

Tool calls are JSON inside `<tool_call>` tags. Unknown or malformed tool calls are converted into tool-response errors rather than crashing the whole trajectory.

## Skill Mechanism

`knowledge_tool.py` defines eight static skills:

- `spatial_layout`
- `aesthetic_drawing`
- `text_rendering`
- `creative_drawing`
- `anatomy_body_coherence`
- `attribute_binding`
- `physical_material_consistency`
- `quantity_counting`

`KnowledgeTool.call(skill_name=...)` validates the requested name, loads markdown from `knowledge/skills`, and returns a `## Skill Guidance` block. The README notes that training-time RL augments this with dynamic visual experience memory, but the public runtime only exposes static markdown skills.

Gen-Retry should reuse the small static skill-bank pattern for Stage 2 and add Geneval-specific routing around failures such as `count_mismatch`, `color_mismatch`, and `spatial_mismatch`.

## Prompt-Reference Program Format

The final assistant answer must be:

```json
{
  "gen_prompt": "natural language generation prompt using ordinal reference phrases",
  "reference_images": [
    {"img_id": "IMG_001", "note": "what to copy from this image"}
  ]
}
```

`GenEvolveAgent._finalize_answer()` resolves `IMG_###` identifiers back to image records, sorts by `img_id`, and caps the reference list to the configured maximum, defaulting to two.

Important behavior to preserve in Gen-Retry:

- The prompt body should not contain raw `IMG_###`, URLs, or local paths.
- The `reference_images` list is the binding surface from generated text back to retrieved assets.
- Ordinal phrases in `gen_prompt` must match the sorted reference list order.

## SFT Data Format

The README describes the released SFT dataset as `GenEvolve-Data-SFT/` with about 9,000 records. Each record contains:

- `messages`: chat-format ReAct trajectory ending in `<answer>{gen_prompt, reference_images}</answer>`
- `images`: reference JPEGs used by the multimodal training example

The local repository does not include the full SFT data or the full training scripts. For Gen-Retry, use a self-contained trajectory schema with `messages`-compatible steps and a separate `normalized_diagnostic` field so future builders can emit Qwen3-VL-compatible ShareGPT records.

## Training Script Structure

The public repository is an inference and evaluation runtime, not a full trainer. Relevant scripts:

- `scripts/serve_vllm.sh`: serve the released policy through an OpenAI-compatible endpoint.
- `scripts/run_agent.py`: load prompts, run `GenEvolveAgent`, and incrementally write `results.json`.
- `scripts/generate_images.py`: render saved prompt-reference programs with Qwen-Image-Edit service, local Qwen debug mode, or Nano Banana Pro.
- `scripts/evaluate_images.py`: Gemini-style benchmark judge with OpenAI-compatible multimodal chat-completions.

The README explicitly says full training scripts are not included. Do not infer hidden trainer APIs from this public tree.

## Filtering And Guardrails

Filtering appears in the runtime and prompt policy rather than a separate data-filtering script:

- `image_search` drops results without a downloaded `local_path`.
- duplicate image URLs/local paths map to the same `IMG_###`.
- final references are resolved only if the `img_id` exists.
- final references are sorted by `IMG_###` and capped.
- the system prompt requires strict de-duplication by person, object, event moment, and setting.
- final-step override forbids more tool calls and forces an answer.

For Gen-Retry, implement comparable guardrails around diagnostic trajectories:

- preserve passed constraints explicitly before repair.
- reject references to unknown tool outputs or unknown skills.
- cap retry steps in future stages.
- keep final submission tied to a successful diagnostic pass or a documented unresolved failure.
