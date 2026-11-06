"""The extract stage: send each changed unit once, store what the validator accepts.

Extraction is per unit but the runner calls `process` per import item, so the first call extracts every
unit whose text differs from the stored one, newest first, up to `max_calls`; the rest are deferred to
the next run. `process` then only reports each item's unit: failed re-raises, deferred leaves the item
pending, anything else is done.
"""

import hashlib
import sqlite3

from librarian.extract import persist, runs, units
from librarian.importer.stages import Deferred, Stage
from librarian.ports import Extractor


def stale_units(conn: sqlite3.Connection, workspace: str) -> list[units.Unit]:
    """Units whose text changed since their last successful extraction, newest first."""
    stored = dict(
        conn.execute("SELECT unit_key, text_hash FROM extracted_units WHERE workspace = ?", (workspace,))
    )
    distinct = {u.key: u for group in units.build(conn, workspace).values() for u in group}
    stale = [u for u in distinct.values() if stored.get(u.key) != _hash(u)]
    return sorted(stale, key=lambda u: (-u.newest, u.key))


def stage(workspace: str, extractor: Extractor, max_calls: int | None = None) -> Stage:
    by_item: dict[tuple[str, str], list[units.Unit]] | None = None
    failed: dict[str, Exception] = {}
    deferred: set[str] = set()
    made = 0

    def extract_stale(conn: sqlite3.Connection) -> None:
        nonlocal by_item, made
        by_item = units.build(conn, workspace)
        stale = stale_units(conn, workspace)
        limit = len(stale) if max_calls is None else max(0, max_calls)
        for unit in stale[:limit]:
            made += 1
            try:
                result = runs.extract_and_record(
                    conn, workspace, extractor, extractor.meta, unit.key, unit.text, [], unit.locators
                )
                persist.persist(conn, workspace, unit.key, _hash(unit), result.records)
            except Exception as exc:
                failed[unit.key] = exc
        deferred.update(u.key for u in stale[limit:])

    def process(conn: sqlite3.Connection, source: str, item: str) -> None:
        if by_item is None:
            extract_stale(conn)
        for unit in by_item.get((source, item), []):
            if unit.key in failed:
                raise failed[unit.key]
            if unit.key in deferred:
                raise Deferred(unit.key)

    def summary() -> str:
        line = f"extraction: {made} calls made, {len(deferred)} units remaining"
        return f"{line}; run import again to continue" if deferred else line

    return Stage("extract", process, counter="extracted", summary=summary)


def _hash(unit: units.Unit) -> str:
    return hashlib.sha256(unit.text.encode()).hexdigest()
