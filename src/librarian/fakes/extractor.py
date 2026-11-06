"""Fake extractor: canned output per unit key from `<fixtures>/extraction/<key>.json`.

The fixture holds one of: {"result": <json>} (serialized), {"raw": "<text>"} (returned verbatim, for
bad JSON / bad ids / invented quotes), or {"error": "<message>"} (raised).
{"calls": [<one of those>, ...]} answers each call for the unit in turn (a re-extraction, a re-run).
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
        earlier = sum(
            1
            for c in self._log.read()
            if c["engine"] == "extractor" and c["args"]["unit_key"] == unit_key
        )
        self._log.record(
            "extractor", "extract", unit_key=unit_key, candidates=[c["id"] for c in candidates]
        )
        path = self._dir / f"{unit_key}.json"
        if not path.exists():
            return json.dumps(
                {"records": []}
            )  # a unit nobody wrote a fixture for has nothing to extract
        canned = json.loads(path.read_text())
        if (
            "calls" in canned
        ):  # the Nth call for this unit gets the Nth entry (the last one repeats)
            canned = canned["calls"][min(earlier, len(canned["calls"]) - 1)]
        if "error" in canned:
            raise ExtractionError(canned["error"])
        if "raw" in canned:
            return canned["raw"]
        return json.dumps(canned["result"], ensure_ascii=False)
