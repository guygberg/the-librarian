# Transcription benchmark

Runs the shortlisted local engines on a folder of recordings and writes a side-by-side report.
Fully local: no uploads, no paid APIs. The script sets `HF_HUB_OFFLINE=1` for every engine run,
so models must be downloaded beforehand. Plain Python 3 standard library for the harness;
engines import their own packages.

## Setup on the work Mac (Apple Silicon)

```bash
brew install ffmpeg cmake
python3 -m venv ~/bench-venv && source ~/bench-venv/bin/activate
pip install mlx-whisper faster-whisper huggingface_hub

# whisper.cpp
git clone https://github.com/ggml-org/whisper.cpp ~/whisper.cpp && cd ~/whisper.cpp
cmake -B build && cmake --build build -j --config Release     # Metal is on by default on Apple Silicon

# models (one-off, needs network; run the benchmark itself offline)
huggingface-cli download ivrit-ai/whisper-large-v3-turbo-ggml --local-dir ~/models/ivrit-whisper-large-v3-turbo-ggml
huggingface-cli download ivrit-ai/whisper-large-v3-turbo-ct2  --local-dir ~/models/ivrit-whisper-large-v3-turbo-ct2
huggingface-cli download mlx-community/whisper-large-v3-turbo --local-dir ~/models/mlx-whisper-large-v3-turbo
huggingface-cli download deepdml/faster-whisper-large-v3-turbo-ct2 --local-dir ~/models/faster-whisper-large-v3-turbo
# ivrit.ai has no MLX build: convert the HF checkpoint with mlx-examples/whisper/convert.py
#   (see https://github.com/ml-explore/mlx-examples/blob/main/whisper/README.md), output to
#   ~/models/ivrit-whisper-large-v3-turbo-mlx
```

Check the ggml file name inside the ivrit download and fix `model` in your config. The stock
faster-whisper turbo repo id above is a community CT2 conversion; any CT2 large-v3-turbo works.

## Run

```bash
cp tools/transcription-benchmark/engines.example.json ~/bench-engines.json   # edit paths
# put recordings in ~/bench-audio, named name.en.m4a / name.he.m4a / name.mixed.m4a
python3 tools/transcription-benchmark/bench.py --config ~/bench-engines.json --audio ~/bench-audio --out ~/bench-out
open ~/bench-out/report.html
```

- `--only-engine NAME` runs one engine; `--force` redoes finished runs; `--dry-run` lists the plan.
- Each engine runs in its own child process, so peak memory is per run.
- To measure cold vs warm start, run the same engine twice with `--force` and compare wall time.
- To prove nothing leaves the machine, run once with Wi-Fi off.
- Check the harness itself anywhere with `tools/transcription-benchmark/selftest.sh` (needs ffmpeg).

## Outputs (`--out`)

- `runs/<engine>/<file>.json`: wall time, real-time factor (RTF), peak RSS, segments with
  timestamps, language and confidence fields, and `uncertain` reasons.
- `results.csv`, `report.md`: one row per file and engine.
- `report.html`: one table per recording, engines side by side, Hebrew right-to-left, uncertain
  passages highlighted with the reason on hover.

## What is flagged uncertain

A segment is flagged when any of: avg_logprob < -1.0, compression_ratio > 2.4, no_speech_prob > 0.6,
min word probability < 0.15, a fallback temperature was used, or the script contradicts the
language hint in the file name. Thresholds live in `engines.DEFAULT_THRESHOLDS` and can be
overridden per engine with `"thresholds": {...}`. Flags mean low model confidence, never "wrong".

## Not covered (do by hand after reading the report)

WER/CER need a hand-corrected reference for a few minutes per file. Timestamp error, hallucination
and dropped-span counts, code-switch word accuracy and diarization (pyannote community-1) are
judged from the report or added later. whisper.cpp's JSON may not give per-token probabilities
and MLX word probabilities are unconfirmed: the adapters record them when present; check one
`runs/*/*.json` first.
