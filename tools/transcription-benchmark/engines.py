"""Engine adapters for the transcription benchmark.

Each adapter turns one audio file into a list of normalised segments:
  {start, end, text, language, avg_logprob, no_speech_prob, compression_ratio,
   temperature, min_word_prob}
Fields an engine cannot give are None. Everything runs locally; nothing is uploaded.
Adapters that need Python packages import them lazily, so `bench.py --list` and
`--dry-run` work on any machine.
"""

import json
import os
import re
import subprocess
import tempfile


def _seg(start, end, text, language=None, **kw):
    return {
        "start": float(start), "end": float(end), "text": text.strip(), "language": language,
        "avg_logprob": kw.get("avg_logprob"), "no_speech_prob": kw.get("no_speech_prob"),
        "compression_ratio": kw.get("compression_ratio"), "temperature": kw.get("temperature"),
        "min_word_prob": kw.get("min_word_prob"),
    }


def _min_word_prob(words):
    probs = [w.get("probability") for w in (words or []) if w.get("probability") is not None]
    return min(probs) if probs else None


def _from_whisper_dict(result, language):
    """Segments from an openai-whisper / mlx-whisper result dict."""
    out = []
    for s in result.get("segments", []):
        out.append(_seg(s["start"], s["end"], s["text"], language or result.get("language"),
                        avg_logprob=s.get("avg_logprob"), no_speech_prob=s.get("no_speech_prob"),
                        compression_ratio=s.get("compression_ratio"), temperature=s.get("temperature"),
                        min_word_prob=_min_word_prob(s.get("words"))))
    return out


# --- whisper.cpp -----------------------------------------------------------

def run_whispercpp(audio, cfg):
    """cfg: binary (whisper-cli), model (ggml .bin), language ('he', 'en', 'auto'), vad_model (optional)."""
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "in.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", audio, "-ar", "16000", "-ac", "1", wav], check=True)
        prefix = os.path.join(tmp, "out")
        cmd = [cfg["binary"], "-m", cfg["model"], "-f", wav, "-l", cfg.get("language", "auto"),
               "-ojf", "-of", prefix]
        if cfg.get("vad_model"):
            cmd += ["--vad", "-vm", cfg["vad_model"]]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(prefix + ".json", encoding="utf-8") as f:
            data = json.load(f)
    lang = data.get("result", {}).get("language")
    out = []
    for item in data.get("transcription", []):
        off = item.get("offsets", {})
        tokens = [t for t in item.get("tokens", []) if not t.get("text", "").startswith("[_")]
        probs = [t["p"] for t in tokens if "p" in t]
        mean_lp = None
        out.append(_seg(off.get("from", 0) / 1000, off.get("to", 0) / 1000, item.get("text", ""), lang,
                        min_word_prob=min(probs) if probs else None, avg_logprob=mean_lp))
    return out


# --- MLX Whisper -----------------------------------------------------------

def run_mlx(audio, cfg):
    """cfg: model (local dir or repo id of an MLX-format model), language."""
    import mlx_whisper  # noqa: PLC0415

    lang = cfg.get("language")
    result = mlx_whisper.transcribe(audio, path_or_hf_repo=cfg["model"], word_timestamps=True,
                                    language=None if lang in (None, "auto") else lang,
                                    condition_on_previous_text=False)
    return _from_whisper_dict(result, lang)


# --- faster-whisper --------------------------------------------------------

def run_faster_whisper(audio, cfg):
    """cfg: model (local CT2 dir), language, compute_type (default int8), multilingual (per-segment detect)."""
    from faster_whisper import WhisperModel  # noqa: PLC0415

    model = WhisperModel(cfg["model"], device="cpu", compute_type=cfg.get("compute_type", "int8"))
    lang = cfg.get("language")
    segments, info = model.transcribe(audio, word_timestamps=True, vad_filter=cfg.get("vad", True),
                                      language=None if lang in (None, "auto") else lang,
                                      multilingual=bool(cfg.get("multilingual", False)),
                                      condition_on_previous_text=False)
    out = []
    for s in segments:  # generator: decoding happens here
        out.append(_seg(s.start, s.end, s.text, lang or info.language, avg_logprob=s.avg_logprob,
                        no_speech_prob=s.no_speech_prob, compression_ratio=s.compression_ratio,
                        temperature=s.temperature,
                        min_word_prob=_min_word_prob([{"probability": w.probability} for w in (s.words or [])])))
    return out


def run_fake(audio, cfg):
    """Self-test runtime: no model, returns canned segments. Used by selftest.sh."""
    return [_seg(0, 2, "hello team", "en", avg_logprob=-0.3, no_speech_prob=0.01, compression_ratio=1.1, temperature=0.0, min_word_prob=0.8),
            _seg(2, 5, "שלום לכולם", "he", avg_logprob=-1.4, no_speech_prob=0.02, compression_ratio=1.2, temperature=0.2, min_word_prob=0.05)]


ADAPTERS = {"fake": run_fake, "whispercpp": run_whispercpp, "mlx": run_mlx, "faster-whisper": run_faster_whisper}


# --- uncertainty flags -----------------------------------------------------

DEFAULT_THRESHOLDS = {
    "avg_logprob_below": -1.0,      # library default for "decoding failed"
    "compression_ratio_above": 2.4,  # repeated-loop / hallucination signal
    "no_speech_prob_above": 0.6,
    "min_word_prob_below": 0.15,     # OpenAI's own hallucination check treats this as anomalous
}
_HEB = re.compile(r"[֐-׿]")
_LAT = re.compile(r"[A-Za-z]")


def flag_segment(seg, thr=None, expected_language=None):
    """Return the reasons a segment is low confidence (empty list if none). Never says 'wrong'."""
    t = {**DEFAULT_THRESHOLDS, **(thr or {})}
    why = []
    if seg["avg_logprob"] is not None and seg["avg_logprob"] < t["avg_logprob_below"]:
        why.append(f"avg_logprob {seg['avg_logprob']:.2f}")
    if seg["compression_ratio"] is not None and seg["compression_ratio"] > t["compression_ratio_above"]:
        why.append(f"compression_ratio {seg['compression_ratio']:.2f}")
    if seg["no_speech_prob"] is not None and seg["no_speech_prob"] > t["no_speech_prob_above"]:
        why.append(f"no_speech_prob {seg['no_speech_prob']:.2f}")
    if seg["min_word_prob"] is not None and seg["min_word_prob"] < t["min_word_prob_below"]:
        why.append(f"min_word_prob {seg['min_word_prob']:.2f}")
    if seg["temperature"]:
        why.append(f"fallback temperature {seg['temperature']}")
    if expected_language == "he" and _LAT.search(seg["text"]) and not _HEB.search(seg["text"]):
        why.append("expected Hebrew, got Latin script")
    if expected_language == "en" and _HEB.search(seg["text"]):
        why.append("expected English, got Hebrew script")
    return why
