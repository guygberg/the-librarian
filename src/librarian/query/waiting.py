"""`librarian waiting`: items pending on someone, and who owns the next step."""

import sqlite3
from datetime import datetime
from typing import Any

from librarian import config
from librarian.query import core, envelope
from librarian.query.open_items import KINDS
from librarian.query.project import _owner


def next_step_owner(view: dict[str, Any]) -> str | None:
    """Whoever the item waits on; failing that, whoever owns it."""
    link = next((link["to"] for link in view["links"] if link["type"] == "waiting_on"), None)
    return view.get("waiting_on") or link or _owner(view)


def waiting(conn: sqlite3.Connection, workspace: str, at: datetime | None = None) -> dict[str, Any]:
    at = at or core.now()
    cfg = config.load()
    ids = [
        row[0]
        for row in conn.execute(
            f"SELECT id FROM records WHERE workspace = ? AND kind IN ({', '.join('?' * len(KINDS))}) ORDER BY id",
            (workspace, *KINDS),
        )
    ]
    views = [v for v in (core.current_view(conn, workspace, rid, cfg, at) for rid in ids) if v["lifecycle"] == "pending"]
    return envelope.build(
        conn,
        workspace,
        cfg,
        views,
        at=at,
        waiting=[{"record_id": v["id"], "title": v["title"], "next_step_owner": next_step_owner(v)} for v in views],
    )
