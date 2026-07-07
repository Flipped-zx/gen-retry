# Run Commands

This file keeps copy-ready commands for cross-machine runs.

Rule of thumb:

- Commit and push this file with each new handoff command.
- Prefer variable-based commands to avoid broken long-path line wrapping.
- Do not paste API keys here.

## GPU Machine: Round4 Selective Canonical Qwen Generation

Run on the GPU machine:

```bash
cd /home/develop/biocloudplantform/xxr/gen-retry
git pull
mkdir -p data/run_logs

META=data/exchange/api_to_gpu/balanced100x5_round4_retry_gpt55_v2_selective_canonical/generation_metadata.jsonl
OUT=data/qwen_geneval2_balanced_100x5_round4_retry_gpt55_selective_canonical
LOG=data/run_logs/qwen_balanced100_x5_round4_retry_gpt55_selective_canonical.log
PID=data/run_logs/qwen_balanced100_x5_round4_retry_gpt55_selective_canonical.pid

test -s "$META" || { echo "missing metadata: $META"; exit 1; }

nohup env CUDA_VISIBLE_DEVICES=0,1,2,3,4,5 python3 scripts/generate_qwen_geneval_images.py --metadata "$META" --output-dir "$OUT" --model-path /home/develop/biocloudplantform/xxr/models/Qwen-Image-2512 --n-samples 1 --limit 64 --seed 1000 --gpus 0,1,2,3,4,5 --workers-per-gpu 1 --dtype bfloat16 --width 1664 --height 928 --steps 40 --true-cfg-scale 4.0 --negative-prompt " " --skip-grid --resume --progress-interval 60 > "$LOG" 2>&1 & echo $! > "$PID"
```

Watch progress:

```bash
tail -f data/run_logs/qwen_balanced100_x5_round4_retry_gpt55_selective_canonical.log
```

## GPU Machine: Round4 Selective Canonical GenEval2 Diagnosis

Run this after Qwen generation is complete. Use the `geneval2` Python environment.

```bash
cd /home/develop/biocloudplantform/xxr/gen-retry
mkdir -p data/run_logs

GEN_OUT=data/qwen_geneval2_balanced_100x5_round4_retry_gpt55_selective_canonical
MANIFEST="$GEN_OUT/generation_manifest.jsonl"
EVAL_SHARDS=data/geneval2_jobs/balanced100x5_round4_retry_gpt55_selective_canonical_shards
GENEVAL2_ROOT=/home/develop/biocloudplantform/xxr/GenEval2
QWEN3VL_MODEL=/home/develop/biocloudplantform/xxr/models/Qwen3-VL-8B-Instruct
PYTHON_BIN=$(which python3)

test -s "$MANIFEST" || { echo "missing manifest: $MANIFEST"; exit 1; }
test -d "$GENEVAL2_ROOT" || { echo "missing GenEval2 root: $GENEVAL2_ROOT"; exit 1; }
test -d "$QWEN3VL_MODEL" || { echo "missing Qwen3VL model: $QWEN3VL_MODEL"; exit 1; }

for i in 0 1 2 3 4 5; do
  mkdir -p "$EVAL_SHARDS/shard_$i"
  nohup env CUDA_VISIBLE_DEVICES=$i "$PYTHON_BIN" scripts/run_geneval2_batch.py --manifest "$MANIFEST" --output-dir "$EVAL_SHARDS/shard_$i" --geneval2-root "$GENEVAL2_ROOT" --qwen3vl-model-path "$QWEN3VL_MODEL" --method soft_tifa_gm --atom-threshold 0.9 --limit 64 --n-samples 1 --num-shards 6 --shard-index "$i" --resume > "data/run_logs/geneval2_round4_selective_canonical_shard_$i.log" 2>&1 &
  echo $! > "data/run_logs/geneval2_round4_selective_canonical_shard_$i.pid"
done
```

Watch all shard logs:

```bash
tail -f data/run_logs/geneval2_round4_selective_canonical_shard_*.log
```

Merge shards after all 6 logs finish:

```bash
cd /home/develop/biocloudplantform/xxr/gen-retry

EVAL_SHARDS=data/geneval2_jobs/balanced100x5_round4_retry_gpt55_selective_canonical_shards
MERGED_EVAL=data/geneval2_jobs/balanced100x5_round4_retry_gpt55_selective_canonical

python3 scripts/merge_geneval2_shards.py --shard-glob "$EVAL_SHARDS/shard_*" --output-dir "$MERGED_EVAL" --expected-count 64
```

Package lightweight GPU-to-API handoff:

```bash
cd /home/develop/biocloudplantform/xxr/gen-retry

GEN_OUT=data/qwen_geneval2_balanced_100x5_round4_retry_gpt55_selective_canonical
MANIFEST="$GEN_OUT/generation_manifest.jsonl"
MERGED_EVAL=data/geneval2_jobs/balanced100x5_round4_retry_gpt55_selective_canonical
HANDOFF=data/exchange/gpu_to_api/balanced100x5_round4_retry_gpt55_v2_selective_canonical

python3 scripts/package_geneval2_handoff.py --generation-manifest "$MANIFEST" --geneval2-dir "$MERGED_EVAL" --output-dir "$HANDOFF" --expected-count 64 --include-atom-rows
```

Commit and push the handoff back to the API machine:

```bash
cd /home/develop/biocloudplantform/xxr/gen-retry

HANDOFF=data/exchange/gpu_to_api/balanced100x5_round4_retry_gpt55_v2_selective_canonical

git add "$HANDOFF"
git commit -m "add round4 selective canonical gpu handoff"
git push
```

## GPU Machine: Round4 Selective Normal Qwen Generation

This is the non-canonical round4 comparison run over the same 64 selected round3 samples.

Run on the GPU machine:

```bash
cd /home/develop/biocloudplantform/xxr/gen-retry
git pull
mkdir -p data/run_logs

META=data/exchange/api_to_gpu/balanced100x5_round4_retry_gpt55_v2_selective_normal/generation_metadata.jsonl
OUT=data/qwen_geneval2_balanced_100x5_round4_retry_gpt55_selective_normal
LOG=data/run_logs/qwen_balanced100_x5_round4_retry_gpt55_selective_normal.log
PID=data/run_logs/qwen_balanced100_x5_round4_retry_gpt55_selective_normal.pid

test -s "$META" || { echo "missing metadata: $META"; exit 1; }

nohup env CUDA_VISIBLE_DEVICES=0,1,2,3,4,5 python3 scripts/generate_qwen_geneval_images.py --metadata "$META" --output-dir "$OUT" --model-path /home/develop/biocloudplantform/xxr/models/Qwen-Image-2512 --n-samples 1 --limit 64 --seed 1000 --gpus 0,1,2,3,4,5 --workers-per-gpu 1 --dtype bfloat16 --width 1664 --height 928 --steps 40 --true-cfg-scale 4.0 --negative-prompt " " --skip-grid --resume --progress-interval 60 > "$LOG" 2>&1 & echo $! > "$PID"
```

Watch progress:

```bash
tail -f data/run_logs/qwen_balanced100_x5_round4_retry_gpt55_selective_normal.log
```

## GPU Machine: Round4 Selective Normal GenEval2 Diagnosis

Run this after the normal Qwen generation is complete. Use the `geneval2` Python environment.

```bash
cd /home/develop/biocloudplantform/xxr/gen-retry
mkdir -p data/run_logs

GEN_OUT=data/qwen_geneval2_balanced_100x5_round4_retry_gpt55_selective_normal
MANIFEST="$GEN_OUT/generation_manifest.jsonl"
EVAL_SHARDS=data/geneval2_jobs/balanced100x5_round4_retry_gpt55_selective_normal_shards
GENEVAL2_ROOT=/home/develop/biocloudplantform/xxr/GenEval2
QWEN3VL_MODEL=/home/develop/biocloudplantform/xxr/models/Qwen3-VL-8B-Instruct
PYTHON_BIN=$(which python3)

test -s "$MANIFEST" || { echo "missing manifest: $MANIFEST"; exit 1; }
test -d "$GENEVAL2_ROOT" || { echo "missing GenEval2 root: $GENEVAL2_ROOT"; exit 1; }
test -d "$QWEN3VL_MODEL" || { echo "missing Qwen3VL model: $QWEN3VL_MODEL"; exit 1; }

for i in 0 1 2 3 4 5; do
  mkdir -p "$EVAL_SHARDS/shard_$i"
  nohup env CUDA_VISIBLE_DEVICES=$i "$PYTHON_BIN" scripts/run_geneval2_batch.py --manifest "$MANIFEST" --output-dir "$EVAL_SHARDS/shard_$i" --geneval2-root "$GENEVAL2_ROOT" --qwen3vl-model-path "$QWEN3VL_MODEL" --method soft_tifa_gm --atom-threshold 0.9 --limit 64 --n-samples 1 --num-shards 6 --shard-index "$i" --resume > "data/run_logs/geneval2_round4_selective_normal_shard_$i.log" 2>&1 &
  echo $! > "data/run_logs/geneval2_round4_selective_normal_shard_$i.pid"
done
```

Watch all shard logs:

```bash
tail -f data/run_logs/geneval2_round4_selective_normal_shard_*.log
```

Merge shards after all 6 logs finish:

```bash
cd /home/develop/biocloudplantform/xxr/gen-retry

EVAL_SHARDS=data/geneval2_jobs/balanced100x5_round4_retry_gpt55_selective_normal_shards
MERGED_EVAL=data/geneval2_jobs/balanced100x5_round4_retry_gpt55_selective_normal

python3 scripts/merge_geneval2_shards.py --shard-glob "$EVAL_SHARDS/shard_*" --output-dir "$MERGED_EVAL" --expected-count 64
```

Package lightweight GPU-to-API handoff:

```bash
cd /home/develop/biocloudplantform/xxr/gen-retry

GEN_OUT=data/qwen_geneval2_balanced_100x5_round4_retry_gpt55_selective_normal
MANIFEST="$GEN_OUT/generation_manifest.jsonl"
MERGED_EVAL=data/geneval2_jobs/balanced100x5_round4_retry_gpt55_selective_normal
HANDOFF=data/exchange/gpu_to_api/balanced100x5_round4_retry_gpt55_v2_selective_normal

python3 scripts/package_geneval2_handoff.py --generation-manifest "$MANIFEST" --geneval2-dir "$MERGED_EVAL" --output-dir "$HANDOFF" --expected-count 64 --include-atom-rows
```

Commit and push the handoff back to the API machine:

```bash
cd /home/develop/biocloudplantform/xxr/gen-retry

HANDOFF=data/exchange/gpu_to_api/balanced100x5_round4_retry_gpt55_v2_selective_normal

git add "$HANDOFF"
git commit -m "add round4 selective normal gpu handoff"
git push
```
