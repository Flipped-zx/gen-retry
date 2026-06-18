"""Export Gen-Retry SFT rows into downstream chat fine-tuning formats."""

from __future__ import annotations

from typing import Any


SUPPORTED_EXPORT_FORMATS = ("qwen", "sharegpt", "trl")

SHAREGPT_CONTEXT = (
    "Execute the Gen-Retry assistant-only target sequence. "
    "Non-assistant context, raw detector outputs, tool observations, and mock judge outputs "
    "are masked in the source trajectory and are not train targets."
)


def export_sft_records(rows: list[dict[str, Any]], export_format: str) -> list[dict[str, Any]]:
    """Export SFT rows to one supported format."""

    if export_format not in SUPPORTED_EXPORT_FORMATS:
        allowed = ", ".join(SUPPORTED_EXPORT_FORMATS)
        raise ValueError(f"unsupported export format {export_format!r}; expected one of: {allowed}")
    return [export_sft_record(row, export_format) for row in rows]


def export_sft_record(row: dict[str, Any], export_format: str) -> dict[str, Any]:
    """Export one full-episode SFT row.

    The source row's ``assistant_trainable_messages`` field is the sole source
    of training text. Raw detector outputs, tool observations, user messages,
    generated image metadata, and mock retry diagnostics are intentionally not
    copied into exported train targets.
    """

    assistant_messages = _assistant_trainable_messages(row)
    row_id = str(row.get("id") or row.get("trajectory_id") or "")
    target_types = [str(message.get("target_type", "")) for message in assistant_messages]
    metadata = _metadata(row, target_types)

    if export_format == "qwen":
        return {
            "id": row_id,
            "format": "qwen_chat",
            "messages": [
                {"role": "assistant", "content": str(message["content"])}
                for message in assistant_messages
            ],
            "loss_mask": [True for _ in assistant_messages],
            "metadata": metadata,
        }

    if export_format == "sharegpt":
        return {
            "id": row_id,
            "format": "sharegpt_llama_factory",
            "conversations": [
                {"from": "human", "value": SHAREGPT_CONTEXT},
                {"from": "gpt", "value": _join_targets(assistant_messages)},
            ],
            "trainable_from": ["gpt"],
            "metadata": metadata,
        }

    if export_format == "trl":
        return {
            "id": row_id,
            "format": "trl_conversational",
            "messages": [
                {"role": "assistant", "content": str(message["content"])}
                for message in assistant_messages
            ],
            "trainable_roles": ["assistant"],
            "metadata": metadata,
        }

    raise AssertionError(f"unhandled export format: {export_format}")


def _assistant_trainable_messages(row: dict[str, Any]) -> list[dict[str, Any]]:
    messages = row.get("assistant_trainable_messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError(f"row {row.get('id', '<unknown>')} has no assistant_trainable_messages")

    out: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise ValueError(f"row {row.get('id', '<unknown>')} assistant message {index} is not an object")
        if message.get("role") != "assistant":
            raise ValueError(f"row {row.get('id', '<unknown>')} trainable message {index} is not assistant")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"row {row.get('id', '<unknown>')} trainable message {index} has empty content")
        out.append(message)
    return out


def _metadata(row: dict[str, Any], target_types: list[str]) -> dict[str, Any]:
    return {
        "source_id": str(row.get("id") or row.get("trajectory_id") or ""),
        "source_trajectory_format": str(row.get("trajectory_format") or ""),
        "target_types": target_types,
        "trainable_source": "assistant_trainable_messages",
        "masking_policy": {
            "train": [
                "assistant diagnostic summaries",
                "assistant tool calls",
                "assistant skill routing",
                "assistant retry decisions",
                "assistant repair prompts",
                "assistant submit/discard decisions",
            ],
            "exclude": [
                "raw Geneval detector outputs",
                "tool observations",
                "generated image metadata",
                "mock judge outputs",
                "user messages",
            ],
        },
    }


def _join_targets(messages: list[dict[str, Any]]) -> str:
    return "\n\n".join(str(message["content"]) for message in messages)
