#!/usr/bin/env python3
"""Repeatable local transcription benchmark.

Runs every engine in a config on every recording in a folder, fully locally (it never
opens a network connection; set HF_HUB_OFFLINE=1 and pre-download models), and writes:

  <out>/runs/<engine>/<file>.json   transcript segments + flags + metrics
  <out>/results.csv                 one row per (file, engine): time, RTF, peak memory, counts
  <out>/report.html                 side-by-side transcripts per file, uncertain passages marked
  <out>/report.md                   the same tables in plain text

Usage:
  python3 bench.py --config engines.json --audio ~/bench-audio --out ~/bench-out
  python3 bench.py --config engines.json --audio ~/bench-audio --out ~/bench-out --dry-run
  python3 bench.py --list

Each engine runs in its own child process, so peak memory (max RSS) is measured per run
and a crash in one engine does not stop the rest. Re-running skips finished runs unless
--force is given. Recording names may carry a language hint: name.en.m4a, name.he.m4a,
name.mixed.m4a (used only for the "expected language" flag and the report grouping).
"""

import argparse
import csv
import html
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path

import engines

AUDIO_EXT = {".wav", ".mp3", ".m4a", ".mp4", ".aac", ".flac", ".ogg", ".mov", ".webm"}


def audio_duration(path):
    """Seconds, via ffprobe."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def language_hint(path):
    parts = Path(path).stem.split(".")
    return parts[-1] if len(parts) > 1 and parts[-1] in ("en", "he", "mixed") else None


def peak_rss_mb(usage):
    # ru_maxrss is bytes on macOS, kilobytes on Linux.
    return usage.ru_maxrss / (1024 * 1024) if sys.platform == "darwin" else usage.ru_maxrss / 1024


def child_main(args):
    """Run one engine on one file inside this (child) process and print JSON to stdout."""
    cfg = json.loads(args.child_cfg)
    t0 = time.monotonic()
    segs = engines.ADAPTERS[cfg["runtime"]](args.child_audio, cfg)
    peak = max(peak_rss_mb(resource.getrusage(resource.RUSAGE_SELF)),
               peak_rss_mb(resource.getrusage(resource.RUSAGE_CHILDREN)))  # children: whisper.cpp subprocess
    print(json.dumps({"segments": segs, "seconds": time.monotonic() - t0, "peak_rss_mb": peak}))


def run_one(engine_cfg, audio, out_file, force, dry_run):
    if out_file.exists() and not force:
        return json.loads(out_file.read_text(encoding="utf-8"))
    dur = audio_duration(audio) if not dry_run else 0.0
    if dry_run:
        print(f"  would run {engine_cfg['name']} on {audio.name}")
        return None
    t0 = time.monotonic()
    p = subprocess.run([sys.executable, __file__, "--child-audio", str(audio),
                        "--child-cfg", json.dumps(engine_cfg)],
                       capture_output=True, text=True, env={**os.environ, "HF_HUB_OFFLINE": "1"})
    wall = time.monotonic() - t0
    result = {"engine": engine_cfg["name"], "file": audio.name, "audio_seconds": dur, "wall_seconds": wall,
              "rtf": wall / dur if dur else None,
              "peak_rss_mb": None,
              "error": None, "segments": []}
    if p.returncode != 0:
        result["error"] = p.stderr.strip()[-2000:]
    else:
        data = json.loads(p.stdout.strip().splitlines()[-1])
        expected = language_hint(audio)
        for s in data["segments"]:
            s["uncertain"] = engines.flag_segment(s, engine_cfg.get("thresholds"),
                                                  expected if expected != "mixed" else None)
        result["segments"] = data["segments"]
        result["engine_seconds"] = data["seconds"]
        result["peak_rss_mb"] = data["peak_rss_mb"]
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def fmt_t(sec):
    sec = int(sec)
    return f"{sec // 3600:d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def write_reports(results, names, out):
    files = sorted({r["file"] for r in results})
    with open(out / "results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "engine", "audio_s", "wall_s", "rtf", "peak_rss_mb", "segments", "uncertain_segments",
                    "uncertain_audio_s", "error"])
        for r in results:
            unc = [s for s in r["segments"] if s.get("uncertain")]
            w.writerow([r["file"], r["engine"], round(r["audio_seconds"], 1), round(r["wall_seconds"], 1),
                        r["rtf"] and round(r["rtf"], 3), r["peak_rss_mb"] and round(r["peak_rss_mb"]),
                        len(r["segments"]), len(unc), round(sum(s["end"] - s["start"] for s in unc), 1),
                        (r["error"] or "")[:80]])
    md = [f"# Transcription benchmark\n\nMachine: {platform.platform()} / {platform.machine()}  ",
          f"Run: {time.strftime('%Y-%m-%d %H:%M')}\n",
          "| file | engine | audio | wall | RTF | peak MB | segments | uncertain |", "|---|---|---|---|---|---|---|---|"]
    h = ["<!doctype html><meta charset=utf-8><title>Transcription benchmark</title><style>"
         "body{font:14px system-ui;margin:1.5rem}table{border-collapse:collapse;width:100%;table-layout:fixed}"
         "td,th{border:1px solid #ccc;padding:.4rem;vertical-align:top}th{background:#f3f3f3}"
         ".he{direction:rtl;text-align:right}.u{background:#fff1b8;border-bottom:2px solid #d9a300}"
         ".t{color:#888;font-size:11px}.err{color:#b00}</style><h1>Transcription benchmark</h1>"
         "<p>Yellow = low model confidence (never proof of an error). Hover for the reason.</p>"]
    for fname in files:
        rs = [r for r in results if r["file"] == fname]
        h.append(f"<h2>{html.escape(fname)}</h2><table><tr>" + "".join(
            f"<th>{html.escape(r['engine'])}<br><span class=t>{r['wall_seconds']:.0f}s, RTF "
            f"{(r['rtf'] or 0):.2f}, {r['peak_rss_mb'] and round(r['peak_rss_mb']) or '?'} MB</span></th>"
            for r in rs) + "</tr><tr>")
        for r in rs:
            unc = [s for s in r["segments"] if s.get("uncertain")]
            md.append(f"| {fname} | {r['engine']} | {fmt_t(r['audio_seconds'])} | {r['wall_seconds']:.0f}s | "
                      f"{(r['rtf'] or 0):.2f} | {r['peak_rss_mb'] and round(r['peak_rss_mb']) or '?'} | "
                      f"{len(r['segments'])} | {len(unc)} |" + (" ERROR" if r["error"] else ""))
            if r["error"]:
                h.append(f"<td class=err>{html.escape(r['error'])}</td>")
                continue
            cells = []
            for s in r["segments"]:
                cls = "u" if s.get("uncertain") else ""
                tip = html.escape("; ".join(s.get("uncertain") or []))
                rtl = " he" if any("֐" <= c <= "׿" for c in s["text"]) else ""
                cells.append(f"<p class='{rtl.strip()}'><span class=t>{fmt_t(s['start'])}</span> "
                             f"<span class='{cls}' title='{tip}'>{html.escape(s['text'])}</span></p>")
            h.append("<td>" + "".join(cells) + "</td>")
        h.append("</tr></table>")
    (out / "report.html").write_text("".join(h), encoding="utf-8")
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config")
    ap.add_argument("--audio", help="folder of recordings")
    ap.add_argument("--out", help="output folder")
    ap.add_argument("--only-engine", help="run just this engine name")
    ap.add_argument("--force", action="store_true", help="re-run finished runs")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list", action="store_true", help="show the runtimes this script supports")
    ap.add_argument("--child-audio")
    ap.add_argument("--child-cfg")
    args = ap.parse_args()

    if args.child_audio:
        return child_main(args)
    if args.list:
        print("runtimes:", ", ".join(engines.ADAPTERS))
        return
    if not (args.config and args.audio and args.out):
        ap.error("--config, --audio and --out are required")
    cfgs = json.loads(Path(args.config).read_text(encoding="utf-8"))["engines"]
    for c in cfgs:  # expand ~ in path-like values
        for k in ("binary", "model", "vad_model"):
            if k in c:
                c[k] = os.path.expanduser(c[k])
    if args.only_engine:
        cfgs = [c for c in cfgs if c["name"] == args.only_engine]
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found: brew install ffmpeg")
    audio_files = sorted(p for p in Path(args.audio).expanduser().iterdir() if p.suffix.lower() in AUDIO_EXT)
    out = Path(args.out).expanduser()
    results = []
    for cfg in cfgs:
        print(f"engine {cfg['name']}")
        for a in audio_files:
            r = run_one(cfg, a, out / "runs" / cfg["name"] / f"{a.name}.json", args.force, args.dry_run)
            if r:
                results.append(r)
                print(f"  {a.name}: {'ERROR' if r['error'] else str(round(r['wall_seconds'])) + 's'}")
    if results:
        write_reports(results, [c["name"] for c in cfgs], out)
        print(f"report: {out / 'report.html'}")


if __name__ == "__main__":
    main()
