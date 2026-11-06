"""Low-confidence segments and uncertain words, computed from the raw metrics stored with each segment.

Computed when shown, not when stored, so changing a threshold in config changes the result without re-transcribing.
The starting thresholds are unvalidated.
"""

from typing import Any


def low_confidence_reasons(segment: dict[str, Any], cfg: dict[str, Any]) -> list[str]:
    checks = (
        ("avg_logprob", segment["avg_logprob"] < cfg["low_confidence_avg_logprob"]),
        ("no_speech_prob", segment["no_speech_prob"] > cfg["low_confidence_no_speech_prob"]),
        ("compression_ratio", segment["compression_ratio"] > cfg["low_confidence_compression_ratio"]),
    )
    return [name for name, hit in checks if hit]


def uncertain_words(segment: dict[str, Any], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Tokens below the probability threshold, each with its character span `[start, end)` in the segment text."""
    text, cursor, found = segment["text"], 0, []
    for token in segment["tokens"]:
        word = token["text"].strip()
        start = text.find(word, cursor)
        if start < 0 or not word:
            continue
        cursor = start + len(word)
        if token["p"] < cfg["uncertain_word_p"]:
            found.append({"text": word, "p": token["p"], "start": start, "end": cursor})
    return found


def describe(segment: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """What `show` adds for a transcript segment; empty when nothing is doubtful."""
    out: dict[str, Any] = {}
    if reasons := low_confidence_reasons(segment, cfg):
        out["confidence"] = {"label": "low confidence", "reasons": reasons}
    if words := uncertain_words(segment, cfg):
        out["uncertain_words"] = words
    return out
