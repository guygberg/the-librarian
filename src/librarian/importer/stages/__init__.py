"""Stage registry. Later tickets replace the placeholders; tests point LIBRARIAN_STAGES at a module with STAGES."""

import importlib
import os
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Stage:
    name: str
    process: Callable[[sqlite3.Connection, str, str], None] = lambda conn, source, item: None
    # Only the first stage introduces items; the rest work on items the earlier stages finished.
    discover: Callable[[sqlite3.Connection], Iterable[tuple[str, str]]] = lambda conn: ()
    counter: str | None = field(default=None)


STAGES = [
    Stage("fetch", counter="fetched"),
    Stage("transcribe", counter="transcribed"),
    Stage("normalise"),
    Stage("extract", counter="extracted"),
    Stage("link"),
]


def load_stages(workspace: str, older: str | None = None) -> list[Stage]:
    override = os.environ.get("LIBRARIAN_STAGES")
    if override:
        return importlib.import_module(override).STAGES
    from librarian import engines  # imported here: both modules import Stage from this one
    from librarian.importer import slack_fetch

    return [slack_fetch.stage(workspace, engines.get_engines(workspace).slack, older), *STAGES[1:]]
