"""`librarian decision <topic>`: why did we decide this, with the reasoning and its Evidence."""

import sqlite3
from datetime import datetime
from typing import Any

from librarian import config
from librarian.query import core, envelope


def _matches(view: dict[str, Any], words: list[str]) -> bool:
    text = " ".join(str(view.get(k, "")) for k in ("title", "body", "reasoning")).lower()
    return all(word in text for word in words)


def decision(conn: sqlite3.Connection, workspace: str, topic: str, at: datetime | None = None) -> dict[str, Any]:
    at = at or core.now()
    cfg = config.load()
    words = topic.lower().split()
    ids = [row[0] for row in conn.execute("SELECT id FROM records WHERE workspace = ? AND kind = 'decision' ORDER BY id", (workspace,))]
    views = [v for v in (core.current_view(conn, workspace, rid, cfg, at) for rid in ids) if words and _matches(v, words)]
    views.sort(key=lambda v: v.get("last_evidence", ""), reverse=True)
    answer = envelope.build(
        conn,
        workspace,
        cfg,
        views,
        at=at,
        decisions=[
            {"record_id": v["id"], "title": v["title"], "reasoning": v.get("reasoning", "not found")} for v in views
        ],
    )
    if not views:
        answer["warnings"].insert(0, {"code": "decision_not_found", "message": f"no decision matches {topic!r}"})
    return answer
