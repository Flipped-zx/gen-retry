# SFT Export Formats

Gen-Retry full episode rows keep training targets separate from context:

- Train from `assistant_trainable_messages`.
- Exclude `tool_observations`.
- Exclude `raw_detector_outputs`.
- Exclude `non_trainable_context` and generated image metadata.
- Exclude `mock_retry_diagnostic` and mock judge outputs.
- Exclude user messages.

The exporters in `src/gen_retry/data/exporters.py` use only `assistant_trainable_messages`.

## Export Commands

Offline candidate-level retry trajectories:

```bash
python3 scripts/export_offline_retry_sft.py \
  --trajectories-dir data/raw_trajectories/geneval2_balanced_100_round0_gpt55 \
  --output data/sft/geneval2_balanced_100_round0_retry_replan_sft.jsonl \
  --rejected-output data/rejected/geneval2_balanced_100_round0_retry_replan_rejected.jsonl
```

This exporter writes one `retry_replan` row per `retry_ready` trajectory. The user message is the persisted teacher request with raw evaluator payloads and local image artifact paths removed by default; the assistant target is the strict `retry_ready_action` JSON.

Legacy full-episode processed rows:

```bash
python3 scripts/export_sft.py \
  --input data/processed/geneval_retry_sft_5_full.jsonl \
  --format qwen \
  --output data/processed/export_qwen_5.jsonl

python3 scripts/export_sft.py \
  --input data/processed/geneval_retry_sft_5_full.jsonl \
  --format sharegpt \
  --output data/processed/export_sharegpt_5.jsonl

python3 scripts/export_sft.py \
  --input data/processed/geneval_retry_sft_5_full.jsonl \
  --format trl \
  --output data/processed/export_trl_5.jsonl
```

Check the exports:

```bash
python3 scripts/check_export_quality.py \
  data/processed/export_qwen_5.jsonl \
  data/processed/export_sharegpt_5.jsonl \
  data/processed/export_trl_5.jsonl
```

## Qwen Chat Format

Output: `data/processed/export_qwen_5.jsonl`

Each row:

```json
{
  "id": "sample_000000",
  "format": "qwen_chat",
  "messages": [
    {"role": "assistant", "content": "<parse_constraints>...</parse_constraints>"},
    {"role": "assistant", "content": "<tool_call>...</tool_call>"}
  ],
  "loss_mask": [true, true],
  "metadata": {}
}
```

This is an assistant-only chat export. The `loss_mask` mirrors the assistant message list so a downstream Qwen exporter can keep loss on assistant targets only.

## ShareGPT / LLaMA-Factory Format

Output: `data/processed/export_sharegpt_5.jsonl`

Each row:

```json
{
  "id": "sample_000000",
  "format": "sharegpt_llama_factory",
  "conversations": [
    {"from": "human", "value": "Execute the Gen-Retry assistant-only target sequence..."},
    {"from": "gpt", "value": "<parse_constraints>...</parse_constraints>\n\n<tool_call>...</tool_call>"}
  ],
  "trainable_from": ["gpt"],
  "metadata": {}
}
```

The human message is a sanitized placeholder. It does not contain raw diagnostics, detector boxes, tool observations, generated image metadata, or mock judge outputs. LLaMA-Factory-style training should keep loss on `gpt` turns only.

## TRL Conversational Format

Output: `data/processed/export_trl_5.jsonl`

Each row:

```json
{
  "id": "sample_000000",
  "format": "trl_conversational",
  "messages": [
    {"role": "assistant", "content": "<parse_constraints>...</parse_constraints>"},
    {"role": "assistant", "content": "<tool_call>...</tool_call>"}
  ],
  "trainable_roles": ["assistant"],
  "metadata": {}
}
```

This is an assistant-only conversational export for TRL-style pipelines. If a later training stack requires user turns, add sanitized non-trainable context in the trainer adapter, not by copying raw detector outputs into this file.

## Quality Rules

`scripts/check_export_quality.py` verifies:

- exported files are valid JSONL;
- train targets contain no `bbox`, detector `score`, raw detector output fields, tool observations, generated image metadata, mock judge outputs, or `<tool_response>` tags;
- train targets contain no API-key-like strings;
- each assistant target sequence includes tool calls, `query_skill`, a repair prompt, retry decision content, and submit/discard content;
- Qwen and TRL exports contain assistant-only messages;
- ShareGPT exports mark only `gpt` messages as trainable.
