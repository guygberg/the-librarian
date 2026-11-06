"""The extract stage: send each unit once, store what the validator accepts.

The runner calls `process` per import item, but extraction is per unit. A unit already stored with the
same text is skipped, so the items of one unit cost one call; a failed unit is remembered for the rest
of the run so its other items do not call the extractor again.
"""

import hashlib
import sqlite3

from librarian.extract import persist, runs, units
from librarian.importer.stages import Stage
from librarian.ports import Extractor


def stage(workspace: str, extractor: Extractor) -> Stage:
    by_item: dict[tuple[str, str], list[units.Unit]] | None = None
    failed: dict[str, Exception] = {}

    def process(conn: sqlite3.Connection, source: str, item: str) -> None:
        nonlocal by_item
        if by_item is None:
            by_item = units.build(conn, workspace)
        for unit in by_item.get((source, item), []):
            if unit.key in failed:
                raise failed[unit.key]
            try:
                _extract(conn, workspace, extractor, unit)
            except Exception as exc:
                failed[unit.key] = exc
                raise

    return Stage("extract", process, counter="extracted")


def _extract(conn: sqlite3.Connection, workspace: str, extractor: Extractor, unit: units.Unit) -> None:
    text_hash = hashlib.sha256(unit.text.encode()).hexdigest()
    stored = conn.execute(
        "SELECT text_hash FROM extracted_units WHERE workspace = ? AND unit_key = ?", (workspace, unit.key)
    ).fetchone()
    if stored and stored[0] == text_hash:
        return
    result = runs.extract_and_record(
        conn, workspace, extractor, extractor.meta, unit.key, unit.text, [], unit.locators
    )
    persist.persist(conn, workspace, unit.key, text_hash, result.records)
