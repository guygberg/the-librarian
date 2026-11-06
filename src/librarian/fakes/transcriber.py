"""Fake transcriber: reads the `<file>.transcript.json` sidecar next to a placeholder recording.

The sidecar's optional `detected_language` is what detection returns (default `en`).
"""

import json
from pathlib import Path

from librarian.fakes.calllog import CallLog
from librarian.ports import Segment, Token


class FakeTranscriber:
    def __init__(self, log: CallLog):
        self._log = log

    def _sidecar(self, file: Path) -> dict:
        sidecar = file.with_name(file.name + ".transcript.json")
        if not sidecar.exists():
            raise FileNotFoundError(f"fake transcriber: no sidecar transcript at {sidecar}")
        return json.loads(sidecar.read_text())

    def detect_language(self, file: Path) -> str:
        self._log.record("transcriber", "detect_language", file=str(file))
        return self._sidecar(file).get("detected_language", "en")

    def transcribe(self, file: Path, model: str, language: str) -> list[Segment]:
        self._log.record("transcriber", "transcribe", file=str(file), model=model, language=language)
        segments = self._sidecar(file)["segments"]
        return [Segment(**{**s, "tokens": [Token(**t) for t in s["tokens"]]}) for s in segments]
