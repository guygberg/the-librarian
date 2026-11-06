"""Forget a Slack conversation: the one place Source items are deleted.

Shared by `librarian forget` (terminal) and `POST /api/forget` (UI). Both take the Import lock first, so a
running Import never sees half a conversation vanish.
"""

import sqlite3
from typing import Any

from librarian import events
from librarian.slack import picks

SOURCE = "slack"


def _marks(ids: list[int]) -> str:
    return ", ".join("?" * len(ids))


def items_of(conn: sqlite3.Connection, workspace: str, conversation_id: str) -> list[tuple[int, str]]:
    return conn.execute(
        "SELECT id, stable_id FROM source_items WHERE workspace = ? AND source = ? AND substr(stable_id, 1, ?) = ?",
        (workspace, SOURCE, len(conversation_id) + 1, f"{conversation_id}/"),
    ).fetchall()


def forget(conn: sqlite3.Connection, workspace: str, conversation_id: str, label: str | None = None) -> dict[str, Any]:
    """Delete the conversation's items and revisions, every Record left with no Evidence, and unpick it."""
    items = items_of(conn, workspace, conversation_id)
    item_ids = [i for i, _ in items]
    conn.execute("BEGIN IMMEDIATE")
    try:
        orphans = _delete_items(conn, workspace, conversation_id, item_ids)
        picks.edit_picks(conn, workspace, unpick=[conversation_id])
        detail = {"conversation": label or conversation_id, "items": len(items), "records": len(orphans)}
        events.append(conn, workspace, None, "forget_conversation", detail)  # commits
    except BaseException:
        conn.rollback()
        raise
    return detail


def _delete_items(conn: sqlite3.Connection, workspace: str, conversation_id: str, item_ids: list[int]) -> list[int]:
    revisions = [
        r for (r,) in conn.execute(
            f"SELECT id FROM source_item_revisions WHERE source_item_id IN ({_marks(item_ids)})", item_ids
        )
    ]
    touched = [
        r for (r,) in conn.execute(
            f"SELECT DISTINCT record_id FROM evidence WHERE revision_id IN ({_marks(revisions)})", revisions
        )
    ] if revisions else []
    if revisions:
        conn.execute(f"DELETE FROM evidence WHERE revision_id IN ({_marks(revisions)})", revisions)
    orphans = [
        r for r in touched
        if not conn.execute("SELECT 1 FROM evidence WHERE record_id = ?", (r,)).fetchone()
    ]
    if orphans:
        marks = _marks(orphans)
        conn.execute(f"UPDATE records SET parent_id = NULL WHERE parent_id IN ({marks})", orphans)
        for table, column in (
            ("review_entries", "record_id"), ("review_entries", "other_record_id"),
            ("project_aliases", "record_id"), ("unit_records", "record_id"),
        ):
            conn.execute(f"DELETE FROM {table} WHERE {column} IN ({marks})", orphans)
        conn.execute(
            f"DELETE FROM links WHERE (from_type = 'record' AND from_id IN ({marks}))"
            f" OR (to_type = 'record' AND to_id IN ({marks}))",
            orphans + orphans,
        )
        conn.execute(f"DELETE FROM records WHERE id IN ({marks})", orphans)
        conn.execute(f"DELETE FROM record_events WHERE record_id IN ({marks})", orphans)  # allowed once the Record is gone
    if item_ids:
        marks = _marks(item_ids)
        conn.execute(
            f"DELETE FROM links WHERE (from_type = 'source_item' AND from_id IN ({marks}))"
            f" OR (to_type = 'source_item' AND to_id IN ({marks}))",
            item_ids + item_ids,
        )
        conn.execute(f"DELETE FROM source_search WHERE source_item_id IN ({marks})", item_ids)
        conn.execute(f"DELETE FROM source_item_revisions WHERE source_item_id IN ({marks})", item_ids)
        conn.execute(f"DELETE FROM source_items WHERE id IN ({marks})", item_ids)
    # The next Import must not think these were fetched or extracted already.
    conn.execute(
        "DELETE FROM import_item_stages WHERE workspace = ? AND source = ? AND substr(item, 1, ?) = ?",
        (workspace, SOURCE, len(conversation_id) + 1, f"{conversation_id}/"),
    )
    conn.execute(
        "DELETE FROM import_items WHERE workspace = ? AND source = ? AND substr(item, 1, ?) = ?",
        (workspace, SOURCE, len(conversation_id) + 1, f"{conversation_id}/"),
    )
    for prefix in ("slack-thread", "slack-day"):
        conn.execute(
            "DELETE FROM extracted_units WHERE workspace = ? AND substr(unit_key, 1, ?) = ?",
            (workspace, len(prefix) + len(conversation_id) + 2, f"{prefix}-{conversation_id}-"),
        )
    return orphans
