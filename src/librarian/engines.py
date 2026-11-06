"""Engine factory: `LIBRARIAN_ENGINES` (or config `engines`) picks `fake` or `real`."""

import os
from pathlib import Path

from librarian import config, paths
from librarian.fakes.calllog import CallLog
from librarian.fakes.extractor import FakeExtractor
from librarian.fakes.slack import FakeSlack
from librarian.fakes.transcriber import FakeTranscriber
from librarian.ports import Engines
from librarian.slack.client import SlackClient
from librarian.transcribe.whisper_cpp import WhisperCppTranscriber


class _NotImplementedYet:
    def __init__(self, name: str):
        self._name = name

    def __getattr__(self, attr: str):
        def fail(*args, **kwargs):
            raise NotImplementedError(f"real {self._name} engine is not implemented yet")

        return fail


def fixtures_dir() -> Path:
    value = os.environ.get("LIBRARIAN_FIXTURES")
    if not value:
        raise RuntimeError("fake engines need LIBRARIAN_FIXTURES to point at a fixtures folder")
    return Path(value)


def call_log(workspace: str) -> CallLog:
    return CallLog(paths.workspace_dir(workspace))


def get_engines(workspace: str = paths.DEFAULT_WORKSPACE) -> Engines:
    mode = os.environ.get("LIBRARIAN_ENGINES") or config.load().get("engines", "real")
    if mode == "real":
        cfg = config.load()
        return Engines(SlackClient.from_config(cfg), WhisperCppTranscriber(cfg), _NotImplementedYet("extractor"))
    if mode != "fake":
        raise ValueError(f"LIBRARIAN_ENGINES must be 'fake' or 'real', got {mode!r}")
    log, fixtures = call_log(workspace), fixtures_dir()
    return Engines(FakeSlack(fixtures, log), FakeTranscriber(log), FakeExtractor(fixtures, log))
