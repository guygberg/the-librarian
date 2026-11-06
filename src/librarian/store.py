"""Source item store. Items are keyed by Workspace + source + stable id; edits add revisions.

This module never deletes items or revisions; `mark_gone` only sets a flag. Only
`librarian.forget` deletes them.
"""

import hashlib
import sqlite3

from librarian import locator, textsearch
from librarian.clock import utc_now_iso


def upsert(
    conn: sqlite3.Connection,
    workspace: str,
    source: str,
    stable_id: str,
    content: str,
    *,
    origin_name: str = "",
    origin_kind: str = "",
) -> bool:
    """Store the item; return True when a new item or a new revision was written."""
    digest = hashlib.sha256(content.encode()).hexdigest()
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO source_items (workspace, source, stable_id, created_at)"
            " VALUES (?, ?, ?, ?)",
            (workspace, source, stable_id, utc_now_iso()),
        )
        item_id = conn.execute(
            "SELECT id FROM source_items WHERE workspace = ? AND source = ? AND stable_id = ?",
            (workspace, source, stable_id),
        ).fetchone()[0]
        conn.execute(
            "UPDATE source_items SET origin_name = ?, origin_kind = ?, gone = 0 WHERE id = ?",
            (origin_name, origin_kind, item_id),
        )
        last = conn.execute(
            "SELECT revision, content_hash FROM source_item_revisions"
            " WHERE source_item_id = ? ORDER BY revision DESC LIMIT 1",
            (item_id,),
        ).fetchone()
        if last and last[1] == digest:
            return False
        conn.execute(
            "INSERT INTO source_item_revisions"
            " (workspace, source_item_id, revision, content_hash, content, fetched_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (workspace, item_id, (last[0] if last else 0) + 1, digest, content, utc_now_iso()),
        )
        text = textsearch.index_text(content)
        conn.execute("DELETE FROM source_search WHERE source_item_id = ?", (item_id,))
        conn.execute(
            "INSERT INTO source_search"
            " (body, workspace, source, stable_id, source_item_id, original)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (textsearch.normalise(text), workspace, source, stable_id, item_id, text),
        )
        return True


def latest_content(
    conn: sqlite3.Connection, workspace: str, source: str, stable_id: str
) -> str | None:
    row = conn.execute(
        "SELECT r.content FROM source_items i"
        " JOIN source_item_revisions r ON r.source_item_id = i.id"
        " WHERE i.workspace = ? AND i.source = ? AND i.stable_id = ?"
        " ORDER BY r.revision DESC LIMIT 1",
        (workspace, source, stable_id),
    ).fetchone()
    return row[0] if row else None


def mark_gone(
    conn: sqlite3.Connection, workspace: str, source: str, stable_id: str, gone: bool = True
) -> None:
    with conn:
        conn.execute(
            "UPDATE source_items SET gone = ? WHERE workspace = ? AND source = ? AND stable_id = ?",
            (int(gone), workspace, source, stable_id),
        )


def gone_ids(conn: sqlite3.Connection, workspace: str, source: str) -> set[str]:
    """Stable ids of the source's items that vanished upstream; their revisions and Evidence stay."""
    rows = conn.execute(
        "SELECT stable_id FROM source_items WHERE workspace = ? AND source = ? AND gone = 1", (workspace, source)
    )
    return {r[0] for r in rows}


def evidence_is_gone(loc: str, gone_slack: set[str]) -> bool:
    parsed = locator.parse(loc)
    return parsed.source == "slack" and parsed.stable_id in gone_slack


def get_item(conn: sqlite3.Connection, workspace: str, source: str, stable_id: str) -> dict | None:
    row = conn.execute(
        "SELECT id, origin_name, origin_kind, gone, created_at FROM source_items"
        " WHERE workspace = ? AND source = ? AND stable_id = ?",
        (workspace, source, stable_id),
    ).fetchone()
    if row is None:
        return None
    revisions = conn.execute(
        "SELECT revision, content_hash, content, fetched_at FROM source_item_revisions"
        " WHERE source_item_id = ? ORDER BY revision",
        (row[0],),
    ).fetchall()
    return {
        "workspace": workspace,
        "source": source,
        "stable_id": stable_id,
        "origin_name": row[1],
        "origin_kind": row[2],
        "flags": {"gone_from_source": bool(row[3])},
        "created_at": row[4],
        "revisions": [
            {"revision": r[0], "content_hash": r[1], "content": r[2], "fetched_at": r[3]}
            for r in revisions
        ],
    }
