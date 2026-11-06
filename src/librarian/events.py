"""Person events on a Record: an append-only log. The HTTP actions come later; they and tests append through here.

`detail` keys the current view understands (see `librarian.query.core`):
- `lifecycle` (+ optional `waiting_on`, `suspended_by`, `reason`): status_change, resolve_disagreement
- `person_id`: owner_change; `project_id`: project_move
Every other event is history only until the action that needs it lands.
"""

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

TYPES = (
    "status_change", "owner_change", "project_move", "accept_suggestion", "reject_suggestion",
    "merge", "split", "dismiss", "set_speaker", "resolve_disagreement",
)


def append(
    conn: sqlite3.Connection, workspace: str, record_id: int, event: str, detail: dict[str, Any] | None = None,
    at: str | None = None,
) -> int:
    if event not in TYPES:
        raise ValueError(f"unknown event {event!r}")
    with conn:
        return conn.execute(
            "INSERT INTO record_events (workspace, record_id, event, detail, at) VALUES (?, ?, ?, ?, ?)",
            (workspace, record_id, event, json.dumps(detail or {}), at or datetime.now(UTC).isoformat()),
        ).lastrowid


def for_record(conn: sqlite3.Connection, workspace: str, record_id: int) -> list[dict[str, Any]]:
    return [
        {"event": event, "detail": json.loads(detail), "at": at}
        for event, detail, at in conn.execute(
            "SELECT event, detail, at FROM record_events WHERE workspace = ? AND record_id = ? ORDER BY id",
            (workspace, record_id),
        )
    ]
