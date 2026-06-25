#!/usr/bin/env python3
"""Run official GenEval2 evaluation for one prompt/image and emit atom rows."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


DEFAULT_QWEN3VL_MODEL_PATH = "/root/private_data/agentic_image/models/Qwen3-VL-8B-Instruct"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate one generated image with official GenEval2.")
    parser.add_argument("--geneval2-root", default="../GenEval2")
    parser.add_argument("--benchmark-data", default="../GenEval2/geneval2_data.jsonl")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--image-path", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--method", default="soft_tifa_gm", choices=["vqascore", "tifa", "soft_tifa_am", "soft_tifa_gm"])
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--qwen3vl-model-path",
        default=DEFAULT_QWEN3VL_MODEL_PATH,
        help=(
            "Local Qwen3-VL model path. Defaults to the hard-coded project model path."
        ),
    )
    args = parser.parse_args()

    benchmark_row, source_index = _find_benchmark_row(args.benchmark_data, args.prompt)
    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix="geneval2_single_") as tmp:
        tmpdir = Path(tmp)
        single_benchmark = tmpdir / "benchmark.jsonl"
        image_map = tmpdir / "image_paths.json"
        score_lists_path = tmpdir / "score_lists.json"
        evaluation_script = _prepare_evaluation_script(
            Path(args.geneval2_root),
            tmpdir,
            qwen3vl_model_path=args.qwen3vl_model_path,
        )

        single_benchmark.write_text(
            json.dumps(benchmark_row, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        image_map.write_text(
            json.dumps({benchmark_row["prompt"]: args.image_path}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        subprocess.run(
            [
                args.python,
                str(evaluation_script),
                "--benchmark_data",
                str(single_benchmark),
                "--image_filepath_data",
                str(image_map),
                "--method",
                args.method,
                "--output_file",
                str(score_lists_path),
            ],
            cwd=str(Path(args.geneval2_root)),
            check=True,
        )
        score_lists = json.loads(score_lists_path.read_text(encoding="utf-8"))

    if not isinstance(score_lists, list) or not score_lists or not isinstance(score_lists[0], list):
        raise ValueError(f"unexpected GenEval2 score list format in {score_lists_path}")
    rows = _atom_rows(
        benchmark_row,
        source_index=source_index,
        image_path=args.image_path,
        scores=score_lists[0],
    )
    output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} GenEval2 atom row(s) -> {output_path}")
    return 0


def _prepare_evaluation_script(
    geneval2_root: Path,
    tmpdir: Path,
    *,
    qwen3vl_model_path: str | None,
) -> Path:
    source = geneval2_root / "evaluation.py"
    if not qwen3vl_model_path:
        return source
    text = source.read_text(encoding="utf-8")
    if "Qwen/Qwen3-VL-8B-Instruct" not in text:
        raise ValueError(f"could not find Qwen3-VL model id in {source}")
    patched = text.replace("Qwen/Qwen3-VL-8B-Instruct", qwen3vl_model_path)
    target = tmpdir / "evaluation_local_qwen3vl.py"
    target.write_text(patched, encoding="utf-8")
    return target


def _find_benchmark_row(path: str | Path, prompt: str) -> tuple[dict[str, Any], int]:
    for index, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        row = json.loads(line)
        if isinstance(row, dict) and row.get("prompt") == prompt:
            return row, index
    raise KeyError(f"prompt not found in {path}: {prompt!r}")


def _atom_rows(
    row: dict[str, Any],
    *,
    source_index: int,
    image_path: str,
    scores: list[Any],
) -> list[dict[str, Any]]:
    vqa_list = row.get("vqa_list", [])
    skills = row.get("skills", [])
    atom_rows: list[dict[str, Any]] = []
    for atom_index, score in enumerate(scores):
        question = ""
        answer = ""
        if isinstance(vqa_list, list) and atom_index < len(vqa_list):
            pair = vqa_list[atom_index]
            if isinstance(pair, list) and len(pair) >= 2:
                question = str(pair[0])
                answer = str(pair[1])
        skill = ""
        if isinstance(skills, list) and atom_index < len(skills):
            skill = str(skills[atom_index])
        atom_rows.append(
            {
                "prompt_id": row.get("prompt"),
                "source_index": source_index,
                "prompt": row.get("prompt", ""),
                "atom_count": row.get("atom_count"),
                "atom_index": atom_index,
                "question": question,
                "answer": answer,
                "score": score,
                "skill": skill,
                "image_id": image_path,
                "image_path": image_path,
            }
        )
    return atom_rows


if __name__ == "__main__":
    raise SystemExit(main())
