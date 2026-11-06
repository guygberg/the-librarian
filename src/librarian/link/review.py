"""Review entries: the data behind the Review list (rendered by a later ticket)."""

import sqlite3
from datetime import UTC, datetime
from typing import Any

UNCONFIRMED_PERSON = "unconfirmed_person"
UNKNOWN_SPEAKER = "unknown_speaker"
INFERRED_PROJECT = "inferred_project"
SUGGESTED_PROJECT = "suggested_project"
MERGE_PROJECT = "merge_project"
MARKS = {
    UNCONFIRMED_PERSON: "unconfirmed person",
    UNKNOWN_SPEAKER: "unknown speaker",
    INFERRED_PROJECT: "inferred project",
    SUGGESTED_PROJECT: "suggested project",
    MERGE_PROJECT: "possible duplicate project",
}


def add(
    conn: sqlite3.Connection, workspace: str, kind: str, record_id: int, link_type: str, raw_name: str | None,
    other_record_id: int | None = None,
) -> None:
    """Idempotent: a re-extraction that reaches the same doubt does not list it twice."""
    same = conn.execute(
        "SELECT 1 FROM review_entries WHERE workspace = ? AND kind = ? AND record_id = ? AND link_type = ?"
        " AND raw_name IS ? AND other_record_id IS ? AND resolved_at IS NULL",
        (workspace, kind, record_id, link_type, raw_name, other_record_id),
    ).fetchone()
    if same:
        return
    conn.execute(
        "INSERT INTO review_entries (workspace, kind, record_id, link_type, raw_name, other_record_id, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (workspace, kind, record_id, link_type, raw_name, other_record_id, datetime.now(UTC).isoformat()),
    )


def for_record(conn: sqlite3.Connection, workspace: str, record_id: int) -> list[dict[str, Any]]:
    return [
        {"kind": kind, "mark": MARKS[kind], "link": link_type, **({"raw_name": raw} if raw else {})}
        for kind, link_type, raw in conn.execute(
            "SELECT kind, link_type, raw_name FROM review_entries"
            " WHERE workspace = ? AND record_id = ? AND resolved_at IS NULL ORDER BY id",
            (workspace, record_id),
        )
    ]


def open_entries(conn: sqlite3.Connection, workspace: str) -> list[dict[str, Any]]:
    return [
        {"id": id_, "record_id": record_id, "kind": kind, "link": link_type, "raw_name": raw, "other_record_id": other}
        for id_, record_id, kind, link_type, raw, other in conn.execute(
            "SELECT id, record_id, kind, link_type, raw_name, other_record_id FROM review_entries"
            " WHERE workspace = ? AND resolved_at IS NULL ORDER BY id",
            (workspace,),
        )
    ]
