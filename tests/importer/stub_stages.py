"""Stub stages driven by env vars, loaded by the CLI through LIBRARIAN_STAGES.

STUB_ITEMS: file of `source/item` lines. STUB_FAIL: `stage:item` that raises. STUB_LOG: file that
gets one `stage item` line per execution. STUB_BLOCK: while this file exists, fetch waits; once
blocked it creates `<STUB_BLOCK>.started`.
"""

import os
import time
from pathlib import Path

from librarian.importer.stages import Stage


def _discover(conn):
    for line in Path(os.environ["STUB_ITEMS"]).read_text().split():
        source, item = line.split("/")
        yield source, item


def _stage(name, counter=None, discover=lambda conn: ()):
    def process(conn, source, item):
        with open(os.environ["STUB_LOG"], "a") as log:
            log.write(f"{name} {item}\n")
        block = os.environ.get("STUB_BLOCK")
        if name == "fetch" and block and Path(block).exists():
            Path(block + ".started").touch()
            while Path(block).exists():
                time.sleep(0.05)
        if os.environ.get("STUB_FAIL") == f"{name}:{item}":
            raise RuntimeError("boom")

    return Stage(name, process, discover, counter)


STAGES = [
    _stage("fetch", "fetched", _discover),
    _stage("transcribe", "transcribed"),
    _stage("normalise"),
    _stage("extract", "extracted"),
    _stage("link"),
]
