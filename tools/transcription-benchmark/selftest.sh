#!/usr/bin/env bash
# Checks the harness itself (timing, memory, flags, reports) with a fake engine. Needs ffmpeg only.
set -euo pipefail
d=$(mktemp -d); trap 'rm -rf "$d"' EXIT
mkdir "$d/audio"
ffmpeg -loglevel error -f lavfi -i "sine=frequency=440:duration=5" "$d/audio/demo.mixed.wav"
echo '{"engines":[{"name":"fake","runtime":"fake"}]}' > "$d/cfg.json"
python3 "$(dirname "$0")/bench.py" --config "$d/cfg.json" --audio "$d/audio" --out "$d/out"
grep -q "fallback temperature" "$d/out/report.html"
grep -q "fake" "$d/out/results.csv"
echo "selftest ok"
