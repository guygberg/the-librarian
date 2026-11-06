"""Review entries: the data behind the Review list (rendered by a later ticket)."""

import sqlite3
from datetime import UTC, datetime
from typing import Any

UNCONFIRMED_PERSON = "unconfirmed_person"
UNKNOWN_SPEAKER = "unknown_speaker"
MARKS = {UNCONFIRMED_PERSON: "unconfirmed person", UNKNOWN_SPEAKER: "unknown speaker"}


def add(conn: sqlite3.Connection, workspace: str, kind: str, record_id: int, link_type: str, raw_name: str | None) -> None:
    conn.execute(
        "INSERT INTO review_entries (workspace, kind, record_id, link_type, raw_name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (workspace, kind, record_id, link_type, raw_name, datetime.now(UTC).isoformat()),
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
        {"id": id_, "record_id": record_id, "kind": kind, "link": link_type, "raw_name": raw}
        for id_, record_id, kind, link_type, raw in conn.execute(
            "SELECT id, record_id, kind, link_type, raw_name FROM review_entries"
            " WHERE workspace = ? AND resolved_at IS NULL ORDER BY id",
            (workspace,),
        )
    ]
