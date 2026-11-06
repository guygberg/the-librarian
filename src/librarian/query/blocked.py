"""`librarian blocked [--project P]`: unfinished blockers and what they block.

What they block are their blocks Links.
"""

import sqlite3
from datetime import datetime
from typing import Any

from librarian import config
from librarian.query import core, envelope, project, stale


def blocked(
    conn: sqlite3.Connection, workspace: str, name: str | None = None, at: datetime | None = None
) -> dict[str, Any]:
    at = at or core.now()
    cfg = config.load()
    resolved: dict[str, Any] = envelope.WORKSPACE_BASELINE
    if name:
        winner, ranked = project.resolve(conn, workspace, name)
        if winner is None:
            return project.unresolved(conn, workspace, cfg, name, ranked, at, blocked=[])
        views = project.member_views(conn, workspace, cfg, winner, at)
        resolved = {"project": {"id": winner, "name": views[0]["title"]}, "baseline": None}
    else:
        rows = conn.execute("SELECT id FROM records WHERE workspace = ? ORDER BY id", (workspace,))
        views = [core.current_view(conn, workspace, rid, cfg, at) for (rid,) in rows]
    blockers = [v for v in views if v["kind"] == "blocker" and v["lifecycle"] in stale.UNFINISHED]
    return envelope.build(
        conn,
        workspace,
        cfg,
        blockers,
        at=at,
        resolved=resolved,
        blocked=[
            {
                "record_id": v["id"],
                "title": v["title"],
                "owner": project._owner(v),
                "blocks": [
                    {"id": link["to_id"], "title": link["to"]}
                    for link in v["links"]
                    if link["type"] == "blocks"
                ],
            }
            for v in blockers
        ],
    )
