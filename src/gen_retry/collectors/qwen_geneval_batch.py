"""Batch collection for Qwen-Image generations and Geneval diagnostics."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
import json
import os
import shlex
import subprocess
import time
from typing import Any

from gen_retry.evaluators.geneval_result_normalizer import (
    normalize_geneval_output,
    teacher_diagnostic_row,
)
from gen_retry.utils.ids import make_episode_id
from gen_retry.utils.io import read_jsonl, write_jsonl
from gen_retry.utils.progress import ProgressMeter


@dataclass(frozen=True)
class CandidateJob:
    run_id: str
    sample_id: str
    candidate_id: str
    prompt: str
    candidate_index: int
    seed: int
    category: str
    expected: dict[str, Any]
    image_path: str
    raw_geneval_path: str
    gpu: str
    qwen_model_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "sample_id": self.sample_id,
            "candidate_id": self.candidate_id,
            "prompt": self.prompt,
            "candidate_index": self.candidate_index,
            "seed": self.seed,
            "category": self.category,
            "expected": self.expected,
            "image_path": self.image_path,
            "raw_geneval_path": self.raw_geneval_path,
            "gpu": self.gpu,
            "qwen_model_path": self.qwen_model_path,
        }


class QwenGenevalBatchCollector:
    """Run or plan Qwen-Image generation followed by Geneval evaluation."""

    def __init__(
        self,
        *,
        prompts_path: str | Path,
        output_dir: str | Path,
        images_per_prompt: int = 4,
        gpus: list[str] | None = None,
        base_seed: int = 1000,
        run_id: str | None = None,
        qwen_model_path: str = "/home/develop/biocloudplantform/xxr/models/Qwen-Image-2512",
    ) -> None:
        self.prompts_path = Path(prompts_path)
        self.output_dir = Path(output_dir)
        self.images_dir = self.output_dir / "images"
        self.raw_geneval_dir = self.output_dir / "geneval_raw"
        self.images_per_prompt = images_per_prompt
        self.gpus = gpus or ["0"]
        self.base_seed = base_seed
        self.run_id = run_id or time.strftime("qwen_geneval_%Y%m%d_%H%M%S")
        self.qwen_model_path = qwen_model_path

    def plan_jobs(self, *, limit: int | None = None) -> list[CandidateJob]:
        prompt_rows = read_jsonl(self.prompts_path)
        if limit is not None:
            prompt_rows = prompt_rows[:limit]
        jobs: list[CandidateJob] = []
        for prompt_index, row in enumerate(prompt_rows):
            prompt = str(row.get("prompt", "")).strip()
            if not prompt:
                raise ValueError(f"{self.prompts_path} row {prompt_index} has empty prompt")
            sample_id = str(
                row.get("prompt_id")
                or row.get("id")
                or row.get("sample_id")
                or make_episode_id(prompt, prompt_index)
            )
            category = str(row.get("category", ""))
            expected = dict(row.get("expected") or {})
            for candidate_index in range(self.images_per_prompt):
                candidate_id = f"{sample_id}_cand_{candidate_index:02d}"
                seed = self.base_seed + prompt_index * self.images_per_prompt + candidate_index
                gpu = self.gpus[len(jobs) % len(self.gpus)]
                jobs.append(
                    CandidateJob(
                        run_id=self.run_id,
                        sample_id=sample_id,
                        candidate_id=candidate_id,
                        prompt=prompt,
                        candidate_index=candidate_index,
                        seed=seed,
                        category=category,
                        expected=expected,
                        image_path=str(self.images_dir / f"{candidate_id}.png"),
                        raw_geneval_path=str(self.raw_geneval_dir / f"{candidate_id}.json"),
                        gpu=gpu,
                        qwen_model_path=self.qwen_model_path,
                    )
                )
        return jobs

    def write_manifest(self, jobs: list[CandidateJob]) -> Path:
        path = self.output_dir / "generation_manifest.jsonl"
        write_jsonl(path, [job.to_dict() for job in jobs])
        return path

    def run_generation(
        self,
        jobs: list[CandidateJob],
        *,
        command_template: str,
        allow_missing_images: bool = False,
        progress_interval: float = 30.0,
    ) -> list[dict[str, Any]]:
        return self._run_jobs(
            jobs,
            command_template=command_template,
            phase="generation",
            validate_image=not allow_missing_images,
            progress_interval=progress_interval,
        )

    def run_geneval(
        self,
        jobs: list[CandidateJob],
        *,
        command_template: str,
        progress_interval: float = 30.0,
    ) -> list[dict[str, Any]]:
        return self._run_jobs(
            jobs,
            command_template=command_template,
            phase="geneval",
            validate_image=False,
            progress_interval=progress_interval,
        )

    def normalize_outputs(
        self,
        jobs: list[CandidateJob],
        *,
        generator_name: str = "qwen-image",
    ) -> tuple[Path, Path]:
        diagnostic_rows: list[dict[str, Any]] = []
        teacher_rows: list[dict[str, Any]] = []
        for job in jobs:
            raw_path = Path(job.raw_geneval_path)
            if not raw_path.exists():
                raise FileNotFoundError(f"missing raw Geneval output: {raw_path}")
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError(f"{raw_path} must contain a JSON object")
            normalized, diagnostic = normalize_geneval_output(
                raw,
                prompt=job.prompt,
                expected=job.expected,
                category=job.category,
            )
            generator_metadata = {
                "generator": generator_name,
                "seed": job.seed,
                "candidate_index": job.candidate_index,
                "gpu": job.gpu,
                "model_path": job.qwen_model_path,
            }
            diagnostic_rows.append(
                {
                    **job.to_dict(),
                    "generator_metadata": generator_metadata,
                    "geneval_report": normalized.to_dict(),
                    "diagnostic": diagnostic,
                }
            )
            teacher_rows.append(
                teacher_diagnostic_row(
                    candidate_id=job.candidate_id,
                    sample_id=job.sample_id,
                    candidate_index=job.candidate_index,
                    prompt=job.prompt,
                    image_path=job.image_path,
                    diagnostic=diagnostic,
                    generator_metadata=generator_metadata,
                )
            )
        diagnostics_path = self.output_dir / "candidate_diagnostics.jsonl"
        teacher_path = self.output_dir / "teacher_diagnostics.jsonl"
        write_jsonl(diagnostics_path, diagnostic_rows)
        write_jsonl(teacher_path, teacher_rows)
        return diagnostics_path, teacher_path

    def _run_jobs(
        self,
        jobs: list[CandidateJob],
        *,
        command_template: str,
        phase: str,
        validate_image: bool,
        progress_interval: float = 30.0,
    ) -> list[dict[str, Any]]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.raw_geneval_dir.mkdir(parents=True, exist_ok=True)
        failures: list[dict[str, Any]] = []
        progress = ProgressMeter(
            len(jobs),
            label=f"qwen-geneval {phase}",
            update_interval=progress_interval,
        )
        progress.update(completed=0, force=True)
        with ThreadPoolExecutor(max_workers=len(self.gpus)) as pool:
            futures = {
                pool.submit(
                    _run_one,
                    job,
                    command_template,
                    phase,
                    validate_image,
                ): job
                for job in jobs
            }
            completed_count = 0
            for future in as_completed(futures):
                result = future.result()
                completed_count += 1
                if result.get("status") != "ok":
                    failures.append(result)
                progress.update(
                    completed=completed_count,
                    force=progress_interval == 0,
                    extra=f"failures={len(failures)}",
                )
        if failures:
            write_jsonl(self.output_dir / f"{phase}_failed.jsonl", failures)
        return failures


def format_command(template: str, job: CandidateJob) -> str:
    context = {
        "run_id": shlex.quote(job.run_id),
        "sample_id": shlex.quote(job.sample_id),
        "candidate_id": shlex.quote(job.candidate_id),
        "prompt": shlex.quote(job.prompt),
        "candidate_index": str(job.candidate_index),
        "seed": str(job.seed),
        "category": shlex.quote(job.category),
        "image_path": shlex.quote(job.image_path),
        "geneval_output_path": shlex.quote(job.raw_geneval_path),
        "gpu": shlex.quote(job.gpu),
        "qwen_model_path": shlex.quote(job.qwen_model_path),
        "prompt_raw": job.prompt,
        "image_path_raw": job.image_path,
        "geneval_output_path_raw": job.raw_geneval_path,
        "qwen_model_path_raw": job.qwen_model_path,
    }
    return template.format(**context)


def _run_one(
    job: CandidateJob,
    command_template: str,
    phase: str,
    validate_image: bool,
) -> dict[str, Any]:
    Path(job.image_path).parent.mkdir(parents=True, exist_ok=True)
    Path(job.raw_geneval_path).parent.mkdir(parents=True, exist_ok=True)
    command = format_command(command_template, job)
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = job.gpu
    started = time.time()
    completed = subprocess.run(
        command,
        shell=True,
        env=env,
        text=True,
        capture_output=True,
    )
    elapsed = time.time() - started
    if phase == "geneval" and not Path(job.raw_geneval_path).exists() and completed.stdout.strip():
        Path(job.raw_geneval_path).write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0:
        return {
            "status": "failed",
            "phase": phase,
            "candidate_id": job.candidate_id,
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "elapsed_seconds": elapsed,
        }
    if validate_image and not Path(job.image_path).exists():
        return {
            "status": "failed",
            "phase": phase,
            "candidate_id": job.candidate_id,
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "elapsed_seconds": elapsed,
            "error": f"expected image was not created: {job.image_path}",
        }
    if phase == "geneval" and not Path(job.raw_geneval_path).exists():
        return {
            "status": "failed",
            "phase": phase,
            "candidate_id": job.candidate_id,
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "elapsed_seconds": elapsed,
            "error": f"expected Geneval JSON was not created: {job.raw_geneval_path}",
        }
    return {
        "status": "ok",
        "phase": phase,
        "candidate_id": job.candidate_id,
        "elapsed_seconds": elapsed,
    }
