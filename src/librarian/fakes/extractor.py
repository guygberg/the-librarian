"""Fake extractor: canned output per unit key from `<fixtures>/extraction/<key>.json`.

The fixture holds one of: {"result": <json>} (serialized), {"raw": "<text>"} (returned verbatim, for
bad JSON / bad ids / invented quotes), or {"error": "<message>"} (raised).
A unit without a fixture returns no Records.
"""

import json
from pathlib import Path

from librarian.extract.runs import RunMeta
from librarian.fakes.calllog import CallLog


class ExtractionError(RuntimeError):
    pass


class FakeExtractor:
    meta = RunMeta(model="fake-model", claude_code_version="0.0.0-fake", prompt="fake prompt")

    def __init__(self, fixtures: Path, log: CallLog):
        self._dir = fixtures / "extraction"
        self._log = log

    def extract(self, unit_key: str, unit_text: str, candidates: list[dict]) -> str:
        self._log.record("extractor", "extract", unit_key=unit_key)
        path = self._dir / f"{unit_key}.json"
        if not path.exists():
            return json.dumps({"records": []})  # a unit nobody wrote a fixture for has nothing to extract
        canned = json.loads(path.read_text())
        if "error" in canned:
            raise ExtractionError(canned["error"])
        if "raw" in canned:
            return canned["raw"]
        return json.dumps(canned["result"], ensure_ascii=False)
