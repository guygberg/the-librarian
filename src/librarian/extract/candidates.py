"""Candidates sent with a unit, so Claude can say same / updated / new and keep Record ids stable.

Always the list of projects; plus the open Records (and those changed within the stale threshold) of the
candidate projects: those already linked to earlier items of the same conversation, session or recording,
and those whose name or Alias appears in the unit's text. The Records are capped so a busy project cannot
fill the call.
"""

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from librarian.extract.units import Unit
from librarian.link import projects
from librarian.link.names import key

RECORD_CAP = 60
_OPEN = ("open", "pending", "suspended")


def pick(conn: sqlite3.Connection, workspace: str, unit: Unit, stale_days: int) -> list[dict[str, Any]]:
    chosen = _same_conversation(conn, workspace, unit) | _named_in(conn, workspace, unit)
    return add_projects(conn, workspace, _project_list(conn, workspace), sorted(chosen), stale_days)


def add_projects(
    conn: sqlite3.Connection, workspace: str, candidates: list[dict[str, Any]], project_ids: list[int], stale_days: int
) -> list[dict[str, Any]]:
    """`candidates` with the Records of these projects added, within what the cap leaves."""
    out = [{**c, "records_sent": True} if c["id"] in project_ids else c for c in candidates]
    sent = {c["id"] for c in out}
    room = RECORD_CAP - sum(1 for c in out if c["kind"] != "project")
    for project_id in project_ids:
        for record in _records_of(conn, workspace, project_id, stale_days):
            if room > 0 and record["id"] not in sent:
                out.append(record)
                sent.add(record["id"])
                room -= 1
    return out


def unsent_projects(records: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[int]:
    """Existing projects the result links Records to, whose own Records were not sent."""
    unsent = {c["id"] for c in candidates if c["kind"] == "project" and not c.get("records_sent")}
    linked = {
        link["to"]["id"]
        for rec in records
        for link in rec.get("links", [])
        if link["type"] == "belongs_to" and "id" in link["to"]
    }
    return sorted(linked & unsent)


def _project_list(conn: sqlite3.Connection, workspace: str) -> list[dict[str, Any]]:
    return [
        {"id": record_id, "kind": "project", "title": title, "records_sent": False}
        for record_id, title in conn.execute(
            "SELECT id, title FROM records WHERE workspace = ? AND kind = 'project' AND lifecycle != 'superseded' ORDER BY id",
            (workspace,),
        )
    ]


def _same_conversation(conn: sqlite3.Connection, workspace: str, unit: Unit) -> set[int]:
    """Projects of Records that cite another item of the conversation, session or recording of this unit."""
    prefixes = {loc.partition("/")[0] + "/" for loc in unit.locators}
    found: set[int] = set()
    for prefix in prefixes:
        rows = conn.execute(
            "SELECT r.id, r.kind FROM records r JOIN evidence e ON e.record_id = r.id"
            " WHERE r.workspace = ? AND substr(e.locator, 1, ?) = ?",
            (workspace, len(prefix), prefix),
        ).fetchall()
        for record_id, kind in rows:
            if kind == "project":
                found.add(record_id)
            else:
                found.update(
                    to_id
                    for (to_id,) in conn.execute(
                        "SELECT to_id FROM links WHERE type = 'belongs_to' AND from_type = 'record' AND from_id = ?"
                        " AND to_type = 'record'",
                        (record_id,),
                    )
                )
    return found


def _named_in(conn: sqlite3.Connection, workspace: str, unit: Unit) -> set[int]:
    text = key(unit.text)
    return {
        record_id
        for record_id, known in projects.names(conn, workspace).items()
        if any(key(name) in text for name in known)
    }


def _records_of(conn: sqlite3.Connection, workspace: str, project_id: int, stale_days: int) -> list[dict[str, Any]]:
    cutoff = (datetime.now(UTC) - timedelta(days=stale_days)).isoformat()
    marks = ", ".join("?" for _ in _OPEN)
    return [
        {"id": record_id, "kind": kind, "title": title, "lifecycle": lifecycle, "project": project_id}
        for record_id, kind, title, lifecycle in conn.execute(
            "SELECT r.id, r.kind, r.title, r.lifecycle FROM records r JOIN links l ON l.from_type = 'record'"
            " AND l.from_id = r.id AND l.type = 'belongs_to' AND l.to_type = 'record' AND l.to_id = ?"
            f" WHERE r.workspace = ? AND (r.lifecycle IN ({marks}) OR r.updated_at >= ?)"
            " ORDER BY r.updated_at DESC, r.id",
            (project_id, workspace, *_OPEN, cutoff),
        )
    ]
