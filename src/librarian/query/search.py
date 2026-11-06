"""Search Source items. Read-only: takes a connection from `db.connect_ro`."""

import sqlite3
from collections.abc import Callable

from librarian import config, locator, textsearch
from librarian.query import core, envelope

SNIPPET_CHARS = 160


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SNIPPET_CHARS else text[:SNIPPET_CHARS].rstrip() + "…"


def _record_ids(conn: sqlite3.Connection, workspace: str, matches: Callable[[str], bool], limit: int) -> list[int]:
    """Records are matched here, not in the full-text index: they change through many writers and a work memory
    bank holds few. Text is the title, body, reasoning, Evidence quotes and a project's aliases; title matches rank first."""
    extra: dict[int, list[str]] = {}
    for table, column in (("evidence", "quote"), ("project_aliases", "alias")):
        for record_id, text in conn.execute(f"SELECT record_id, {column} FROM {table} WHERE workspace = ?", (workspace,)):
            extra.setdefault(record_id, []).append(text)
    titled, other = [], []
    for record_id, title, body, reasoning in conn.execute(
        "SELECT id, title, body, reasoning FROM records WHERE workspace = ? ORDER BY id", (workspace,)
    ):
        if matches(title):
            titled.append(record_id)
        elif matches(" ".join([title, body, reasoning or "", *extra.get(record_id, [])])):
            other.append(record_id)
    return (titled + other)[:limit]


def _people(conn: sqlite3.Connection, workspace: str, matches: Callable[[str], bool]) -> list[dict]:
    people = {pid: {"person_id": pid, "name": name, "aliases": []} for pid, name in conn.execute(
        "SELECT id, name FROM persons WHERE workspace = ? ORDER BY id", (workspace,)
    )}
    for pid, alias in conn.execute("SELECT person_id, alias FROM aliases WHERE workspace = ? ORDER BY id", (workspace,)):
        people[pid]["aliases"].append(alias)
    return [p for p in people.values() if any(matches(label) for label in (p["name"], *p["aliases"]))]


def search(conn: sqlite3.Connection, workspace: str, query: str, limit: int = 20) -> dict:
    """Matching Records are the envelope's `records`; their Evidence, then the raw passages (Source items, role
    `match`, no record_id), make up its `evidence`. People are an extra `people` key."""
    matches = textsearch.matcher(query)
    cfg = config.load()
    at = core.now()
    views = [core.current_view(conn, workspace, rid, cfg, at) for rid in _record_ids(conn, workspace, matches, limit)]
    expression = textsearch.match_expression(query)
    rows = []
    if expression:
        rows = conn.execute(
            "SELECT s.source, s.stable_id, s.original, i.origin_name, i.gone,"
            " (SELECT MAX(fetched_at) FROM source_item_revisions WHERE source_item_id = i.id)"
            " FROM source_search s JOIN source_items i ON i.id = s.source_item_id"
            " WHERE source_search MATCH ? AND s.workspace = ? ORDER BY s.rank LIMIT ?",
            (expression, workspace, limit),
        ).fetchall()
    passages = [
        {
            "record_id": None,
            "source": source,
            "locator": str(locator.Locator(source, stable_id)),
            "quote": _snippet(original),
            "role": "match",
            "retrieved_at": fetched,
            "origin_name": origin_name,
            "gone_from_source": bool(gone),
        }
        for source, stable_id, original, origin_name, gone, fetched in rows
    ]
    evidence = envelope.evidence_for(conn, workspace, [v["id"] for v in views]) + passages
    return envelope.build(conn, workspace, cfg, views, at=at, evidence=evidence, people=_people(conn, workspace, matches))
