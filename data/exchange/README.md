# Git Exchange Area

`data/exchange/` is the only tracked data handoff area for the two-machine loop.
Keep images, raw model outputs, full GenEval2 scratch dirs, API logs, and SFT exports out of Git.

## Direction

- `api_to_gpu/<run>/generation_metadata.jsonl`: API machine output. It tells the GPU machine what retry prompts and paired seeds to generate.
- `gpu_to_api/<run>/`: GPU machine output. It contains `generation_manifest.jsonl`, `normalized_reports.jsonl`, optional `diagnostic_jobs.jsonl`, and `handoff_manifest.json`.

## GPU To API

After image generation and GenEval2 merge on the GPU machine:

```bash
python3 scripts/package_geneval2_handoff.py \
  --generation-manifest data/qwen_geneval2_balanced_100x5_round1_retry_gpt55/generation_manifest.jsonl \
  --geneval2-dir data/geneval2_jobs/balanced100x5_round1_retry_gpt55_merged \
  --output-dir data/exchange/gpu_to_api/balanced100x5_round1_retry_gpt55 \
  --expected-count 471
```

Commit only the new `data/exchange/gpu_to_api/...` directory.

## API To Teacher

After pulling the GPU handoff on the API machine:

```bash
python3 scripts/build_retry_continuation_packages.py \
  --gpu-handoff-dir data/exchange/gpu_to_api/balanced100x5_round1_retry_gpt55 \
  --output-dir data/incoming_generation_results/balanced100x5_round1_retry_gpt55_with_eval \
  --round 1 \
  --trajectory-dir data/raw_trajectories/geneval2_balanced_100x5_round0_gpt55

python3 scripts/build_geneval2_retry_plans.py \
  --package-dir data/incoming_generation_results/balanced100x5_round1_retry_gpt55_with_eval \
  --output-dir data/outgoing_retry_actions/balanced100x5_round1_retry_gpt55 \
  --trajectory-dir data/raw_trajectories/geneval2_balanced_100x5_round0_gpt55 \
  --teacher gpt55 \
  --max-retry 3
```

This updates the same local raw trajectories, preserving the full prompt -> initial plan -> diagnosis -> retry plan sequence.
