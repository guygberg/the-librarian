"""Search Source items. Read-only: takes a connection from `db.connect_ro`."""

import sqlite3

from librarian import config, locator, textsearch
from librarian.query import envelope

SNIPPET_CHARS = 160


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SNIPPET_CHARS else text[:SNIPPET_CHARS].rstrip() + "…"


def search(conn: sqlite3.Connection, workspace: str, query: str, limit: int = 20) -> dict:
    """Passages are Source items, not Records: they are the envelope's `evidence`, role `match`."""
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
    return envelope.build(conn, workspace, config.load(), [], evidence=passages)
