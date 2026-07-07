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

