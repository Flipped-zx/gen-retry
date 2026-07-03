#!/usr/bin/env python3
"""DCU/ROCm entrypoint for Qwen-Image GenEval generation."""

from __future__ import annotations

import sys

from generate_qwen_geneval_images import main


def has_option(argv: list[str], option: str) -> bool:
    return any(arg == option or arg.startswith(option + "=") for arg in argv)


def main_dcu() -> int:
    argv = sys.argv[1:]
    injected: list[str] = []
    if not has_option(argv, "--visible-devices-env"):
        injected.extend(["--visible-devices-env", "HIP_VISIBLE_DEVICES"])
    if not has_option(argv, "--clear-visible-envs"):
        injected.extend(["--clear-visible-envs", "CUDA_VISIBLE_DEVICES,ROCR_VISIBLE_DEVICES"])
    sys.argv = [sys.argv[0], *injected, *argv]
    return main()


if __name__ == "__main__":
    raise SystemExit(main_dcu())
