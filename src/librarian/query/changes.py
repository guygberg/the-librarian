"""`librarian changes [--project P]`: what Import and the person changed since the last meeting."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from librarian import config
from librarian.query import core, envelope, project

FALLBACK_DAYS = 7


def last_meeting(conn: sqlite3.Connection, workspace: str, record_ids: list[int] | None) -> tuple[str, str] | None:
    """(title, date) of the latest recording that is Evidence for one of `record_ids`, or any recording if None."""
    stable_ids = None
    if record_ids is not None:
        marks = ", ".join("?" * len(record_ids))
        stable_ids = {
            loc.removeprefix("drive:").split("#")[0]
            for (loc,) in conn.execute(
                f"SELECT locator FROM evidence WHERE workspace = ? AND locator LIKE 'drive:%' AND record_id IN ({marks})",
                (workspace, *record_ids),
            )
        }
    found = []
    for stable_id, content in conn.execute(
        "SELECT s.stable_id, r.content FROM source_items s JOIN source_item_revisions r ON r.source_item_id = s.id"
        " WHERE s.workspace = ? AND s.source = 'drive'"
        " AND r.revision = (SELECT MAX(revision) FROM source_item_revisions WHERE source_item_id = s.id)",
        (workspace,),
    ):
        segment = json.loads(content)
        if (stable_ids is None or stable_id in stable_ids) and segment.get("date"):
            found.append((segment["date"], segment.get("title", "")))
    date, title = max(found, default=(None, None))
    return (title, date) if date else None


def changes(conn: sqlite3.Connection, workspace: str, name: str | None = None, at: datetime | None = None) -> dict[str, Any]:
    at = at or core.now()
    cfg = config.load()
    scope = None
    resolved: dict[str, Any] = {"project": None, "baseline": None}
    if name:
        winner, ranked = project.resolve(conn, workspace, name)
        if winner is None:
            return project.unresolved(conn, workspace, cfg, name, ranked, at, changes=[])
        scope = [winner, *project._member_ids(conn, workspace, winner)]
        resolved["project"] = {"id": winner, "name": conn.execute("SELECT title FROM records WHERE id = ?", (winner,)).fetchone()[0]}
    meeting = last_meeting(conn, workspace, scope)
    if meeting:
        title, date = meeting
        since = datetime.fromisoformat(date).replace(tzinfo=UTC)
        resolved["baseline"] = f"since the last meeting, {title or 'a recording'}, on {date}"
    else:
        since = at - timedelta(days=FALLBACK_DAYS)
        resolved["baseline"] = f"no meeting found; the last {FALLBACK_DAYS} days, since {since.date().isoformat()}"
    cutoff = since.isoformat()
    in_scope = lambda column: (  # noqa: E731
        ("", ()) if scope is None else (f" AND {column} IN ({', '.join('?' * len(scope))})", tuple(scope))
    )
    sql, args = in_scope("id")
    imported = {
        row[0]: "created" if row[1] >= cutoff else "updated"
        for row in conn.execute(
            f"SELECT id, created_at FROM records WHERE workspace = ? AND updated_at >= ?{sql} ORDER BY id",
            (workspace, cutoff, *args),
        )
    }
    sql, args = in_scope("record_id")
    person = [
        {"record_id": rid, "event": event, "at": when, "change": json.loads(detail)}
        for rid, event, detail, when in conn.execute(
            f"SELECT record_id, event, detail, at FROM record_events WHERE workspace = ? AND at >= ?{sql} ORDER BY id",
            (workspace, cutoff, *args),
        )
    ]
    ids = sorted(imported.keys() | {e["record_id"] for e in person})
    views = [core.current_view(conn, workspace, rid, cfg, at) for rid in ids]
    return envelope.build(
        conn,
        workspace,
        cfg,
        views,
        at=at,
        resolved=resolved,
        since=cutoff,
        changes=[{"record_id": rid, "import": imported.get(rid)} for rid in ids],
        person_events=person,
    )
