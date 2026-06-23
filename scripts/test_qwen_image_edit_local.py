#!/usr/bin/env python3
"""Minimal local Qwen-Image-Edit smoke test."""

from __future__ import annotations

import argparse
from pathlib import Path

import torch
from PIL import Image, ImageDraw
from diffusers import QwenImageEditPlusPipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local Qwen-Image-Edit smoke test.")
    parser.add_argument(
        "--model-path",
        default="/home/develop/biocloudplantform/xxr/models/Qwen-Image-Edit-2511",
    )
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--output", default="qwen_image_edit_local_test.png")
    parser.add_argument("--ref-output", default="qwen_edit_ref.png")
    parser.add_argument(
        "--prompt",
        default="Change the red square into a blue square, keep the white background.",
    )
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--true-cfg-scale", type=float, default=4.0)
    parser.add_argument("--guidance-scale", type=float, default=1.0)
    args = parser.parse_args()

    ref = build_reference_image()
    ref.save(args.ref_output)

    dtype = getattr(torch, args.dtype)
    pipe = QwenImageEditPlusPipeline.from_pretrained(
        args.model_path,
        torch_dtype=dtype,
    )
    pipe = pipe.to(args.device)

    with torch.inference_mode():
        out = pipe(
            image=[ref],
            prompt=args.prompt,
            generator=torch.Generator(device=args.device).manual_seed(args.seed),
            true_cfg_scale=args.true_cfg_scale,
            negative_prompt=" ",
            num_inference_steps=args.steps,
            guidance_scale=args.guidance_scale,
            num_images_per_prompt=1,
        ).images[0]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    out.save(output)
    print(f"saved reference: {args.ref_output}")
    print(f"saved output: {output}")
    return 0


def build_reference_image() -> Image.Image:
    image = Image.new("RGB", (512, 512), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([150, 150, 360, 360], fill="red")
    draw.text((150, 380), "red square", fill="black")
    return image


if __name__ == "__main__":
    raise SystemExit(main())
