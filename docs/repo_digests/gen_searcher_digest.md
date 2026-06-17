# Gen-Searcher Digest

Source inspected read-only from `../Gen-Searcher`.

## Key Tree

```text
../Gen-Searcher/
  README.md
  KnowGen_Eval/
    gpt_eval_knowgen.py
  qwen_image_api_server/
    qwen-image-edit/api.py
  Gen-DeepResearch-SFT/
    LLaMA-Factory/
      data/dataset_info.json
      examples/train_full/gen_qwen3_sft.yaml
  Gen-DeepResearch-RL/
    rllm/
      eval/
        gen_image_from_results.py
        deepresearch_agent.py
        deepresearch_workflow.py
      vision_deepresearch_async_workflow/
        gen_image_deepresearch_agent.py
        gen_image_deepresearch_workflow.py
        gen_image_deepresearch_reward.py
        gen_image_deepresearch_tools_executor.py
        gen_deepresearch_tools_async_executor.py
        data_prepare/register_gen_rl_dataset.py
        tools/gen_web_tools.py
        tools/gen_universal_image_search_impl.py
```

The repository also vendors large RL and training stacks (`verl`, `Megatron-LM`, `LLaMA-Factory`). For Gen-Retry, the relevant project-specific logic is the image deep-research workflow and dataset adapters above.

## Search Tool Format

There are two closely related tool prompts:

- `gen_deepresearch_tools_async_executor.py` exposes `search`, `image_search`, and `visit`.
- `gen_image_deepresearch_agent.py` uses `search`, `image_search`, and `browse`.

The image-generation agent system prompt uses:

- `search`
  - arguments: `{"queries": ["..."], "top_k": 5}`
  - returns title, URL, snippet blocks.
- `image_search`
  - arguments: `{"query": "...", "top_k": 5}`
  - returns numbered image rows with title, URL, local path, and page URL.
- `browse`
  - arguments: `{"url": "...", "query": "..."}`
  - wraps `JinaBrowseTool`; extracts page details through a read proxy plus summarization.

`tools/gen_web_tools.py` is the open-source tool layer. It uses Serper-compatible text and image endpoints through environment variables such as `SERPER_KEY_ID`, `TEXT_SEARCH_API_BASE_URL`, and `IMAGE_SEARCH_API_BASE_URL`. The image search implementation downloads images and normalizes each result to:

```json
{
  "title": "...",
  "url": "...",
  "local_path": "...",
  "page_url": "..."
}
```

## Image Search And Observation Handling

`gen_image_deepresearch_agent.py` parses numbered image-search output, registers each unique local path or URL with `ImageIdManager`, and rewrites the tool observation into `IMG_###` form:

```text
--- image search result for [query] ---
IMG_001: title: ...
  url: ...
  local_path: ...
  page_url: ...
--- end of image search result ---
```

For image-search observations, the first `MAX_IMAGES_PER_SEARCH_FOR_MODEL` local files are also attached to the next user message under an `images` key. That makes the trajectory both textual and multimodal.

For non-image tools, the observation is a normal user message:

```text
<tool_response>
...
</tool_response>
```

Format errors are fed back as user observations. If the model reaches the turn limit, a final message forbids tool calls and asks for an immediate `<answer>`.

## Trajectory Data Format

The image agent returns a result dict with:

- `question`
- `messages`
- `prediction`
- `termination`
- `rounds`
- `time_taken`
- `token_usage`
- `timing`
- response/format flags

`gen_image_deepresearch_workflow.py` converts this into an `Episode`:

- each assistant message becomes a `Step`
- `Step.action` is parsed as `tool_call`, `final_answer`, or `reasoning`
- `Step.observation` is the following `<tool_response>` message when present
- the trajectory reward is filled later by the reward function
- non-answer or prediction-error trajectories are masked

This is a useful pattern for Gen-Retry: keep the raw chat turns, but also extract structured step records for filtering, validation, and future SFT/RL conversion.

## Final Grounded Prompt Format

The final answer must be JSON inside `<answer>`:

```json
{
  "gen_prompt": "...",
  "reference_images": [
    {"img_id": "IMG_001", "note": "..."}
  ]
}
```

The agent validates that `gen_prompt` and `reference_images` exist, resolves each `img_id` through the per-trajectory image map, enriches references with `url`, `local_path`, `title`, and `page_url`, then stores:

```json
{
  "gen_prompt": "...",
  "reference_images": [
    {
      "img_id": "IMG_001",
      "url": "...",
      "local_path": "...",
      "title": "...",
      "page_url": "...",
      "note": "..."
    }
  ]
}
```

`rllm/eval/gen_image_from_results.py` uses `gen_prompt` plus valid `reference_images[*].local_path` when both exist; otherwise it falls back to the original prompt as text-only generation. Qwen edit paths cap references to three images in the reward/generation path.

## SFT Data Construction

The README says SFT training follows LLaMA-Factory using `sft_data.json`. The adapter entry in `Gen-DeepResearch-SFT/LLaMA-Factory/data/dataset_info.json` is:

```json
{
  "gen_sft": {
    "file_name": "sft_data.json",
    "formatting": "sharegpt",
    "columns": {
      "messages": "messages",
      "images": "images"
    },
    "tags": {
      "role_tag": "role",
      "content_tag": "content",
      "user_tag": "user",
      "assistant_tag": "assistant",
      "system_tag": "system"
    }
  }
}
```

The training config `examples/train_full/gen_qwen3_sft.yaml` targets `Qwen/Qwen3-VL-8B-Instruct`, full SFT, `template: qwen3_vl`, `cutoff_len: 32768`, frozen vision tower and projector, and DeepSpeed ZeRO-3.

Gen-Retry should keep Stage 2 examples close to this shape: a future builder can emit `messages` and optional `images`, while retaining internal diagnostic metadata outside the final ShareGPT export.

## RL Data Construction

`vision_deepresearch_async_workflow/data_prepare/register_gen_rl_dataset.py` reads a JSON array with:

- `id`
- `prompt`
- `gt_image`

It validates the GT image path, shuffles, splits train/test, and registers records as:

```json
{
  "id": "...",
  "question": "...",
  "gt_image": "..."
}
```

The image workflow runs the agent on `question`, stores `prediction`, and uses a reward function that may:

- generate an image from `gen_prompt` plus selected references through Qwen-Image-Edit service.
- score generated image vs GT using a GPT-style multimodal judge.
- alternatively score the text answer against the GT image without generation.

This is out of scope for Gen-Retry Stage 2, but the future retry loop should keep the same separation: data item, trajectory, prediction, reward, and mask reason.

## Engineering Takeaways For Gen-Retry

- Use strict XML-ish turn tags for supervised trajectories.
- Keep tool observations as explicit messages, not hidden state.
- Allocate per-trajectory identifiers for generated candidates and diagnostics if future assets are added.
- Store structured predictions separately from raw messages.
- Mask or reject non-answer, parse-failed, or unknown-reference trajectories.
- Keep image generation and reward scoring out of the Stage 2 package.
