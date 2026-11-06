"""Fake transcriber: reads the `<file>.transcript.json` sidecar next to a placeholder recording."""

import json
from pathlib import Path

from librarian.fakes.calllog import CallLog
from librarian.ports import Segment, Token


class FakeTranscriber:
    def __init__(self, log: CallLog):
        self._log = log

    def transcribe(self, file: Path) -> list[Segment]:
        self._log.record("transcriber", "transcribe", file=str(file))
        sidecar = file.with_name(file.name + ".transcript.json")
        if not sidecar.exists():
            raise FileNotFoundError(f"fake transcriber: no sidecar transcript at {sidecar}")
        segments = json.loads(sidecar.read_text())["segments"]
        return [Segment(**{**s, "tokens": [Token(**t) for t in s["tokens"]]}) for s in segments]
