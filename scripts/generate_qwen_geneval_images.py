#!/usr/bin/env python3
"""Generate Qwen-Image samples in the official GenEval image layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gen_retry.data.io import write_jsonl  # noqa: E402
from gen_retry.schemas.actions import InitialPlanAction  # noqa: E402
from gen_retry.utils.progress import ProgressMeter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate N Qwen-Image candidates per GenEval prompt."
    )
    parser.add_argument(
        "--metadata",
        required=True,
        help="GenEval metadata JSONL, e.g. ../geneval/prompts/evaluation_metadata.jsonl.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory in GenEval image layout.")
    parser.add_argument("--model-path", default="Qwen/Qwen-Image")
    parser.add_argument(
        "--initial-plan-dir",
        default="",
        help=(
            "Optional cached initial_plan directory. When set, generation uses "
            "initial_plan.initial_prompt while preserving the original metadata prompt."
        ),
    )
    parser.add_argument("--n-samples", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument(
        "--gpus",
        help=(
            "Comma-separated GPU ids for multi-process generation, e.g. 0,1,2,3. "
            "Each worker sees one accelerator through --visible-devices-env and uses cuda:0. "
            "If the parent visibility env is set, numeric ids are logical ids within it."
        ),
    )
    parser.add_argument(
        "--workers-per-gpu",
        type=int,
        default=1,
        help=(
            "Number of independent generation worker processes to launch on each GPU. "
            "Each worker loads its own Qwen-Image copy, so memory use scales roughly linearly."
        ),
    )
    parser.add_argument(
        "--visible-devices-env",
        default="CUDA_VISIBLE_DEVICES",
        help=(
            "Environment variable used to mask each worker to one accelerator. "
            "Use HIP_VISIBLE_DEVICES on DCU/ROCm machines."
        ),
    )
    parser.add_argument(
        "--clear-visible-envs",
        default="",
        help=(
            "Comma-separated accelerator visibility environment variables to remove "
            "from worker environments before setting --visible-devices-env."
        ),
    )
    parser.add_argument("--num-shards", type=int, default=1, help=argparse.SUPPRESS)
    parser.add_argument("--shard-index", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--width", type=int, default=1664)
    parser.add_argument("--height", type=int, default=928)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--true-cfg-scale", type=float, default=4.0)
    parser.add_argument("--guidance-scale", type=float, default=None)
    parser.add_argument("--negative-prompt", default=" ")
    parser.add_argument(
        "--positive-suffix",
        default="",
        help="Optional suffix appended to each prompt before generation. Defaults to empty.",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-grid", action="store_true")
    parser.add_argument(
        "--progress-interval",
        type=float,
        default=30.0,
        help="Seconds between total progress/ETA updates. Use 0 to print every image.",
    )
    args = parser.parse_args()

    if args.n_samples <= 0:
        raise ValueError("--n-samples must be positive")
    if args.gpus:
        return launch_gpu_workers(args)
    if args.num_shards <= 0:
        raise ValueError("--num-shards must be positive")
    if not 0 <= args.shard_index < args.num_shards:
        raise ValueError("--shard-index must be in [0, --num-shards)")

    metadatas = read_jsonl(Path(args.metadata))
    if args.limit is not None:
        metadatas = metadatas[: args.limit]
    if args.initial_plan_dir:
        metadatas = attach_initial_plans(metadatas, Path(args.initial_plan_dir))
    indexed_metadatas = [
        (prompt_index, metadata)
        for prompt_index, metadata in enumerate(metadatas)
        if prompt_index % args.num_shards == args.shard_index
    ]

    out_dir = Path(args.output_dir)
    validate_indexed_metadatas(
        indexed_metadatas,
        out_dir,
        metadata_path=args.metadata,
        resume=args.resume,
    )
    pipe, torch = load_qwen_pipe(args)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    progress = ProgressMeter(
        len(indexed_metadatas) * args.n_samples,
        label=f"qwen-geneval shard {args.shard_index}/{args.num_shards}",
        update_interval=args.progress_interval,
    )
    progress.update(completed=0, force=True)

    for local_index, (prompt_index, metadata) in enumerate(indexed_metadatas):
        original_prompt = str(metadata.get("prompt", "")).strip()
        prompt = generation_prompt_from_metadata(metadata)
        if not prompt:
            raise ValueError(f"{args.metadata} row {prompt_index} has empty prompt")
        if not original_prompt:
            raise ValueError(f"{args.metadata} row {prompt_index} has empty original prompt")
        sample_dir = out_dir / f"{prompt_index:05d}"
        images_dir = sample_dir / "samples"
        images_dir.mkdir(parents=True, exist_ok=True)
        (sample_dir / "metadata.jsonl").write_text(
            json.dumps(metadata, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        sample_id = str(metadata.get("prompt_id") or f"{prompt_index:05d}")
        generated_paths: list[Path] = []
        for candidate_index in range(args.n_samples):
            image_path = images_dir / f"{candidate_index:05d}.png"
            candidate_seed = candidate_seed_from_metadata(
                metadata,
                base_seed=args.seed,
                prompt_index=prompt_index,
                n_samples=args.n_samples,
                candidate_index=candidate_index,
            )
            if args.resume and image_path.exists():
                generated_paths.append(image_path)
            else:
                image = generate_one(pipe, torch, args, prompt, candidate_seed)
                image.save(image_path)
                generated_paths.append(image_path)
            progress.update(
                force=args.progress_interval == 0,
                extra=f"prompt={prompt_index} candidate={candidate_index}",
            )
            manifest.append(
                {
                    "sample_id": sample_id,
                    "candidate_id": f"{sample_id}_cand_{candidate_index:02d}",
                    "prompt_index": prompt_index,
                    "candidate_index": candidate_index,
                    "seed": candidate_seed,
                    "prompt": prompt,
                    "original_prompt": original_prompt,
                    "generation_prompt": prompt,
                    "generation_prompt_source": metadata.get("generation_prompt_source", "metadata.prompt"),
                    "image_path": str(image_path),
                    "metadata": metadata,
                    "model_path": args.model_path,
                }
            )
        if not args.skip_grid:
            save_grid(generated_paths, sample_dir / "grid.png")
        print(
            f"[qwen-geneval][shard {args.shard_index}/{args.num_shards}] "
            f"{local_index + 1}/{len(indexed_metadatas)} global={prompt_index} {prompt!r}",
            flush=True,
        )

    manifest_path = out_dir / "generation_manifest.jsonl"
    if args.num_shards > 1:
        manifest_path = out_dir / f"generation_manifest.shard_{args.shard_index:02d}.jsonl"
    write_jsonl(manifest_path, manifest)
    print(f"[qwen-geneval] wrote {len(manifest)} images under {out_dir}")
    return 0


def launch_gpu_workers(args: argparse.Namespace) -> int:
    """Launch one subprocess per GPU and merge shard manifests."""

    requested_gpus = [item.strip() for item in str(args.gpus).split(",") if item.strip()]
    gpus = resolve_gpu_ids(requested_gpus, args.visible_devices_env)
    if not gpus:
        raise ValueError("--gpus must contain at least one GPU id")
    if args.workers_per_gpu <= 0:
        raise ValueError("--workers-per-gpu must be positive")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve()
    processes: list[tuple[str, subprocess.Popen[str]]] = []
    worker_gpus = [
        gpu
        for gpu in gpus
        for _ in range(args.workers_per_gpu)
    ]
    for shard_index, gpu in enumerate(worker_gpus):
        env = dict(os.environ)
        for env_name in parse_env_names(args.clear_visible_envs):
            env.pop(env_name, None)
        env[args.visible_devices_env] = gpu
        cmd = worker_command(args, script, shard_index=shard_index, num_shards=len(worker_gpus))
        print(
            f"[qwen-geneval] launch shard {shard_index}/{len(worker_gpus)} "
            f"with {args.visible_devices_env}={gpu}: {' '.join(cmd)}"
        )
        processes.append(
            (
                gpu,
                subprocess.Popen(
                    cmd,
                    env=env,
                    text=True,
                ),
            )
        )

    monitor_generation_progress(args, processes)
    failed: list[tuple[str, int]] = [
        (gpu, int(process.returncode or 0))
        for gpu, process in processes
        if process.returncode not in (0, None)
    ]
    if failed:
        for gpu, returncode in failed:
            print(f"[qwen-geneval] worker on GPU {gpu} failed with return code {returncode}")
        return 1
    merge_shard_manifests(out_dir, len(worker_gpus))
    return 0


def parse_env_names(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def resolve_gpu_ids(requested_gpus: list[str], visible_devices_env: str) -> list[str]:
    """Resolve worker GPU ids, respecting a parent visibility mask."""

    parent_visible = [
        item.strip()
        for item in os.environ.get(visible_devices_env, "").split(",")
        if item.strip()
    ]
    if not parent_visible:
        return requested_gpus
    resolved: list[str] = []
    for item in requested_gpus:
        if item.isdigit():
            index = int(item)
            if 0 <= index < len(parent_visible):
                resolved.append(parent_visible[index])
                continue
        resolved.append(item)
    if resolved != requested_gpus:
        print(
            "[qwen-geneval] resolved logical --gpus "
            f"{','.join(requested_gpus)} within {visible_devices_env}="
            f"{','.join(parent_visible)} -> {','.join(resolved)}"
        )
    return resolved


def worker_command(
    args: argparse.Namespace,
    script: Path,
    *,
    shard_index: int,
    num_shards: int,
) -> list[str]:
    # Use qianwen conda environment python explicitly
    cmd = [
        "/home/develop/data-center/miniconda3/envs/qianwen/bin/python3",
        str(script),
        "--metadata",
        args.metadata,
        "--output-dir",
        args.output_dir,
        "--model-path",
        args.model_path,
        "--n-samples",
        str(args.n_samples),
        "--seed",
        str(args.seed),
        "--device",
        "cuda:0",
        "--num-shards",
        str(num_shards),
        "--shard-index",
        str(shard_index),
        "--dtype",
        args.dtype,
        "--width",
        str(args.width),
        "--height",
        str(args.height),
        "--steps",
        str(args.steps),
        "--true-cfg-scale",
        str(args.true_cfg_scale),
        "--negative-prompt",
        args.negative_prompt,
        "--positive-suffix",
        args.positive_suffix,
        "--progress-interval",
        str(args.progress_interval),
    ]
    if args.initial_plan_dir:
        cmd.extend(["--initial-plan-dir", args.initial_plan_dir])
    if args.limit is not None:
        cmd.extend(["--limit", str(args.limit)])
    if args.guidance_scale is not None:
        cmd.extend(["--guidance-scale", str(args.guidance_scale)])
    if args.resume:
        cmd.append("--resume")
    if args.skip_grid:
        cmd.append("--skip-grid")
    return cmd


def monitor_generation_progress(
    args: argparse.Namespace,
    processes: list[tuple[str, subprocess.Popen[str]]],
) -> None:
    expected = expected_image_count(args)
    out_dir = Path(args.output_dir)
    progress = ProgressMeter(
        expected,
        label="qwen-geneval total",
        update_interval=args.progress_interval,
    )
    progress.update(completed=count_generated_images(out_dir), force=True)
    sleep_seconds = max(1.0, args.progress_interval or 1.0)
    while True:
        alive = any(process.poll() is None for _, process in processes)
        completed = count_generated_images(out_dir)
        progress.update(
            completed=completed,
            force=not alive or args.progress_interval == 0,
            extra=f"workers_alive={sum(1 for _, process in processes if process.poll() is None)}",
        )
        if not alive:
            break
        time.sleep(sleep_seconds)


def expected_image_count(args: argparse.Namespace) -> int:
    metadatas = read_jsonl(Path(args.metadata))
    if args.limit is not None:
        metadatas = metadatas[: args.limit]
    return len(metadatas) * args.n_samples


def count_generated_images(out_dir: Path) -> int:
    if not out_dir.exists():
        return 0
    return sum(1 for _ in out_dir.glob("*/samples/*.png"))


def merge_shard_manifests(out_dir: Path, num_shards: int) -> None:
    merged: list[dict[str, Any]] = []
    for shard_index in range(num_shards):
        shard_path = out_dir / f"generation_manifest.shard_{shard_index:02d}.jsonl"
        if not shard_path.exists():
            raise FileNotFoundError(f"missing shard manifest: {shard_path}")
        merged.extend(read_jsonl(shard_path))
    merged.sort(key=lambda item: (int(item["prompt_index"]), int(item["candidate_index"])))
    write_jsonl(out_dir / "generation_manifest.jsonl", merged)
    print(f"[qwen-geneval] merged {len(merged)} rows -> {out_dir / 'generation_manifest.jsonl'}")


def attach_initial_plans(metadatas: list[dict[str, Any]], plan_dir: Path) -> list[dict[str, Any]]:
    if not plan_dir.exists():
        raise FileNotFoundError(f"initial plan directory does not exist: {plan_dir}")

    planned: list[dict[str, Any]] = []
    for index, metadata in enumerate(metadatas):
        row = dict(metadata)
        prompt_id = prompt_id_from_metadata(row, index)
        plan_path = plan_dir / f"{safe_id(prompt_id)}.json"
        if not plan_path.exists():
            raise FileNotFoundError(f"missing initial plan for {prompt_id}: {plan_path}")
        data = json.loads(plan_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{plan_path} must contain a JSON object")
        action = InitialPlanAction.from_dict(dict(data.get("initial_plan") or {}))
        initial_prompt = action.initial_prompt.strip()
        if not initial_prompt:
            raise ValueError(f"{plan_path} has empty initial_plan.initial_prompt")
        row.setdefault("original_prompt", row.get("prompt", ""))
        row["generation_prompt"] = initial_prompt
        row["generation_prompt_source"] = "initial_plan"
        row["initial_plan_path"] = str(plan_path)
        row["initial_plan_teacher_name"] = data.get("teacher_name")
        row["initial_plan_created_at_unix"] = data.get("created_at_unix")
        row["initial_plan_selected_skills"] = list(action.selected_skills)
        planned.append(row)
    return planned


def generation_prompt_from_metadata(metadata: dict[str, Any]) -> str:
    return str(metadata.get("generation_prompt") or metadata.get("prompt", "")).strip()


def candidate_seed_from_metadata(
    metadata: dict[str, Any],
    *,
    base_seed: int,
    prompt_index: int,
    n_samples: int,
    candidate_index: int,
) -> int:
    metadata_seed = metadata.get("seed")
    if metadata_seed is not None:
        try:
            seed = int(metadata_seed)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"metadata seed must be an integer: {metadata_seed!r}") from exc
        return seed + candidate_index
    return base_seed + prompt_index * n_samples + candidate_index


def validate_indexed_metadatas(
    indexed_metadatas: list[tuple[int, dict[str, Any]]],
    out_dir: Path,
    *,
    metadata_path: str,
    resume: bool,
) -> None:
    for prompt_index, metadata in indexed_metadatas:
        original_prompt = str(metadata.get("prompt", "")).strip()
        prompt = generation_prompt_from_metadata(metadata)
        if not prompt:
            raise ValueError(f"{metadata_path} row {prompt_index} has empty prompt")
        if not original_prompt:
            raise ValueError(f"{metadata_path} row {prompt_index} has empty original prompt")
        if not resume:
            continue
        sample_dir = out_dir / f"{prompt_index:05d}"
        existing_prompt = existing_generation_prompt(sample_dir / "metadata.jsonl")
        if existing_prompt and existing_prompt != prompt:
            raise ValueError(
                f"{sample_dir} already has metadata for a different generation prompt. "
                "Use a fresh --output-dir for plan-conditioned generation, or rerun without --resume "
                "after moving old outputs aside."
            )


def existing_generation_prompt(path: Path) -> str:
    if not path.exists():
        return ""
    rows = read_jsonl(path)
    if not rows:
        return ""
    return generation_prompt_from_metadata(rows[0])


def prompt_id_from_metadata(metadata: dict[str, Any], index: int) -> str:
    value = metadata.get("prompt_id") or metadata.get("id") or metadata.get("sample_id")
    if value:
        return str(value)
    digest = hashlib.sha1(str(metadata.get("prompt", "")).encode("utf-8")).hexdigest()[:10]
    return f"prompt_{index:05d}_{digest}"


def safe_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    return safe or "prompt"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError(f"{path}:{lineno} is not a JSON object")
            records.append(item)
    return records


def load_qwen_pipe(args: argparse.Namespace):
    import torch
    from diffusers import DiffusionPipeline

    dtype = getattr(torch, args.dtype)
    pipe = DiffusionPipeline.from_pretrained(args.model_path, torch_dtype=dtype)
    pipe = pipe.to(args.device)
    return pipe, torch


def generate_one(pipe: Any, torch: Any, args: argparse.Namespace, prompt: str, seed: int):
    generator = torch.Generator(device=args.device).manual_seed(seed)
    kwargs: dict[str, Any] = {
        "prompt": prompt + args.positive_suffix,
        "negative_prompt": args.negative_prompt,
        "width": args.width,
        "height": args.height,
        "num_inference_steps": args.steps,
        "true_cfg_scale": args.true_cfg_scale,
        "generator": generator,
    }
    if args.guidance_scale is not None:
        kwargs["guidance_scale"] = args.guidance_scale
    with torch.inference_mode():
        return pipe(**kwargs).images[0]


def save_grid(paths: list[Path], output: Path) -> None:
    try:
        from PIL import Image
    except ImportError:
        return
    images = [Image.open(path).convert("RGB") for path in paths if path.exists()]
    if not images:
        return
    width, height = images[0].size
    grid = Image.new("RGB", (width * len(images), height))
    for index, image in enumerate(images):
        if image.size != (width, height):
            image = image.resize((width, height))
        grid.paste(image, (index * width, 0))
    grid.save(output)


if __name__ == "__main__":
    raise SystemExit(main())
