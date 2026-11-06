"""The real Transcriber: ffmpeg decodes to 16 kHz mono WAV, whisper.cpp transcribes with a voice-activity pre-pass.

Everything is local. Model files are placed by hand under the data folder (see `librarian doctor`); there is
deliberately no code path that fetches anything.
"""

import json
import math
import re
import shutil
import subprocess
import tempfile
import zlib
from pathlib import Path
from typing import Any

from librarian import paths
from librarian.ports import Segment, Token
from librarian.transcribe.language import ENGLISH_MODEL, HEBREW_MODEL

DETECT_SECONDS = 30
_DETECTED = re.compile(r"auto-detected language:\s*(\w+)")
_SPECIAL_TOKEN = re.compile(r"^\[_.*\]$")


class EngineMissing(RuntimeError):
    """A binary or model file the engine needs is not there; the message names the fix."""


def _missing(what: str, hint: str) -> EngineMissing:
    return EngineMissing(f"{what} is missing: {hint}. Run `librarian doctor` for the full list of fixes.")


def _compression_ratio(text: str) -> float:
    raw = text.encode()
    return len(raw) / len(zlib.compress(raw)) if raw else 0.0


def _segment(item: dict[str, Any]) -> Segment:
    tokens = [
        Token(t["text"], t["p"])
        for t in item.get("tokens", [])
        if "p" in t and not _SPECIAL_TOKEN.match(t.get("text", ""))
    ]
    logprobs = [math.log(max(t.p, 1e-9)) for t in tokens]
    offsets = item.get("offsets", {})
    text = item.get("text", "").strip()
    return Segment(
        start=offsets.get("from", 0) / 1000,
        end=offsets.get("to", 0) / 1000,
        text=text,
        avg_logprob=sum(logprobs) / len(logprobs) if logprobs else 0.0,
        no_speech_prob=item.get("no_speech_prob", 0.0),
        compression_ratio=_compression_ratio(text),
        tokens=tokens,
    )


class WhisperCppTranscriber:
    def __init__(self, cfg: dict[str, Any]):
        models = paths.data_home() / "models"
        self._whisper = cfg.get("whisper_cli", "whisper-cli")
        self._ffmpeg = cfg.get("ffmpeg", "ffmpeg")
        self._models = {
            HEBREW_MODEL: Path(cfg.get("hebrew_model_path") or models / "ivrit-ggml-model.bin"),
            ENGLISH_MODEL: Path(cfg.get("english_model_path") or models / "ggml-large-v3-turbo.bin"),
        }
        self._vad = Path(cfg.get("vad_model_path") or models / "ggml-silero-vad.bin")

    def _binary(self, name: str) -> str:
        found = shutil.which(name)
        if not found:
            raise _missing(f"`{name}`", "install it with Homebrew (`brew install whisper-cpp ffmpeg`)")
        return found

    def _model_file(self, path: Path, what: str) -> str:
        if not path.is_file():
            raise _missing(f"the {what} model file {path}", "copy the model there by hand (URLs are in the docs)")
        return str(path)

    def _decode(self, file: Path, wav: Path, seconds: int | None = None) -> None:
        limit = ["-t", str(seconds)] if seconds else []
        subprocess.run(
            [self._binary(self._ffmpeg), "-y", "-loglevel", "error", "-i", str(file), *limit, "-ar", "16000", "-ac", "1", str(wav)],
            check=True,
            capture_output=True,
        )

    def detect_language(self, file: Path) -> str:
        """`en` when whisper hears English, otherwise `he` (the Hebrew model also covers mixed speech)."""
        cli = self._binary(self._whisper)
        model = self._model_file(self._models[ENGLISH_MODEL], "English")
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "in.wav"
            self._decode(file, wav, DETECT_SECONDS)
            run = subprocess.run([cli, "-m", model, "-f", str(wav), "-dl"], check=True, capture_output=True, text=True)
        found = _DETECTED.search(run.stderr + run.stdout)
        return "en" if found and found.group(1) == "en" else "he"

    def transcribe(self, file: Path, model: str, language: str) -> list[Segment]:
        cli = self._binary(self._whisper)
        model_file = self._model_file(self._models[model], "Hebrew" if model == HEBREW_MODEL else "English")
        vad = self._model_file(self._vad, "voice-activity")
        with tempfile.TemporaryDirectory() as tmp:
            wav, prefix = Path(tmp) / "in.wav", Path(tmp) / "out"
            self._decode(file, wav)
            subprocess.run(
                [cli, "-m", model_file, "-f", str(wav), "-l", language, "--vad", "-vm", vad, "-ojf", "-of", str(prefix)],
                check=True,
                capture_output=True,
            )
            data = json.loads(prefix.with_suffix(".json").read_text(encoding="utf-8"))
        return [_segment(item) for item in data.get("transcription", [])]
