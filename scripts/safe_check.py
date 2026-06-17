#!/usr/bin/env python3
"""
Stdlib-only safety checks for local macOS development.

This script intentionally avoids pytest, pydantic, jsonschema, or any external package.
It is safe to run without installing dependencies.
"""

from __future__ import annotations

import compileall
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def check_python_compile() -> bool:
    ok = True
    for rel in ["src", "scripts", "tests"]:
        path = ROOT / rel
        if path.exists():
            ok = compileall.compile_dir(str(path), quiet=1) and ok
    return ok


def check_json_files() -> bool:
    ok = True
    for rel in ["examples", "schemas", "configs"]:
        path = ROOT / rel
        if not path.exists():
            continue
        for file in path.rglob("*.json"):
            try:
                json.loads(file.read_text(encoding="utf-8"))
            except Exception as exc:
                print(f"[JSON ERROR] {file}: {exc}")
                ok = False
    return ok


def main() -> int:
    ok_compile = check_python_compile()
    ok_json = check_json_files()

    if ok_compile and ok_json:
        print("safe_check passed")
        return 0

    print("safe_check failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
