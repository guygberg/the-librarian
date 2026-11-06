"""Search Source items. Read-only: takes a connection from `db.connect_ro`."""

import sqlite3

from librarian import locator, textsearch

SNIPPET_CHARS = 160


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SNIPPET_CHARS else text[:SNIPPET_CHARS].rstrip() + "…"


def freshness(conn: sqlite3.Connection, workspace: str) -> dict:
    row = conn.execute(
        "SELECT MAX(ended_at) FROM import_runs WHERE workspace = ? AND status = 'finished'", (workspace,)
    ).fetchone()
    return {"last_import_finished_at": row[0]}


def search(conn: sqlite3.Connection, workspace: str, query: str, limit: int = 20) -> dict:
    expression = textsearch.match_expression(query)
    rows = []
    if expression:
        rows = conn.execute(
            "SELECT s.source, s.stable_id, s.original, i.origin_name, i.gone"
            " FROM source_search s JOIN source_items i ON i.id = s.source_item_id"
            " WHERE source_search MATCH ? AND s.workspace = ? ORDER BY s.rank LIMIT ?",
            (expression, workspace, limit),
        ).fetchall()
    return {
        "results": [
            {
                "locator": str(locator.Locator(source, stable_id)),
                "snippet": _snippet(original),
                "source": source,
                "origin_name": origin_name,
                "flags": {"gone_from_source": bool(gone)},
            }
            for source, stable_id, original, origin_name, gone in rows
        ],
        "freshness": freshness(conn, workspace),
    }
