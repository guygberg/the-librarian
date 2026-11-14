"""Candidates sent with a unit, so Claude can say same / updated / new and keep Record ids stable.

Always the list of tags; plus the open Records (and those changed within the stale threshold)
of the candidate tags: those already linked to earlier items of the same conversation, session
or recording, and those whose name or Alias appears in the unit's text. The Records are capped so
a busy tag cannot fill the call.
"""

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from librarian.extract.units import Unit
from librarian.link import tags
from librarian.link.names import key

RECORD_CAP = 60
PERSON_CAP = 200
_OPEN = ("open", "pending", "suspended")


def pick(
    conn: sqlite3.Connection, workspace: str, unit: Unit, stale_days: int
) -> list[dict[str, Any]]:
    chosen = _same_conversation(conn, workspace, unit) | _named_in(conn, workspace, unit)
    return add_tags(conn, workspace, _tag_list(conn, workspace), sorted(chosen), stale_days)


def pick_for_suggestions(
    conn: sqlite3.Connection, workspace: str, unit: Unit, stale_days: int
) -> list[dict[str, Any]]:
    """Every Tag, the open action items near this unit (topped up with the newest open ones, within
    the cap) and every Person with Aliases. All of this workspace, never another."""
    items = [c for c in pick(conn, workspace, unit, stale_days) if c["kind"] == "action_item"]
    items = [{k: v for k, v in c.items() if k != "tag"} for c in items][:RECORD_CAP]
    have = {c["id"] for c in items}
    for record_id, title, lifecycle in conn.execute(
        "SELECT id, title, lifecycle FROM records WHERE workspace = ? AND kind = 'action_item'"
        " AND lifecycle IN (?, ?, ?) ORDER BY updated_at DESC, id",
        (workspace, *_OPEN),
    ):
        if len(items) >= RECORD_CAP:
            break
        if record_id not in have:
            items.append(
                {"id": record_id, "kind": "action_item", "title": title, "lifecycle": lifecycle}
            )
    return [*_tag_list_for_suggestions(conn, workspace), *items, *_persons(conn, workspace)]


def _tag_list_for_suggestions(conn: sqlite3.Connection, workspace: str) -> list[dict[str, Any]]:
    return [{"id": c["id"], "kind": "tag", "title": c["title"]} for c in _tag_list(conn, workspace)]


def _persons(conn: sqlite3.Connection, workspace: str) -> list[dict[str, Any]]:
    aliases: dict[int, list[str]] = {}
    for person_id, alias in conn.execute(
        "SELECT person_id, alias FROM aliases WHERE workspace = ? ORDER BY alias", (workspace,)
    ):
        aliases.setdefault(person_id, []).append(alias)
    return [
        {"id": person_id, "kind": "person", "name": name, "aliases": aliases.get(person_id, [])}
        for person_id, name in conn.execute(
            "SELECT id, name FROM persons WHERE workspace = ? ORDER BY id LIMIT ?",
            (workspace, PERSON_CAP),
        )
    ]


def add_tags(
    conn: sqlite3.Connection,
    workspace: str,
    candidates: list[dict[str, Any]],
    tag_ids: list[int],
    stale_days: int,
) -> list[dict[str, Any]]:
    """`candidates` with the Records of these tags added, within what the cap leaves."""
    out = [{**c, "records_sent": True} if c["id"] in tag_ids else c for c in candidates]
    sent = {c["id"] for c in out}
    room = RECORD_CAP - sum(1 for c in out if c["kind"] != "tag")
    for tag_id in tag_ids:
        for record in _records_of(conn, workspace, tag_id, stale_days):
            if room > 0 and record["id"] not in sent:
                out.append(record)
                sent.add(record["id"])
                room -= 1
    return out


def unsent_tags(records: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[int]:
    """Existing tags the result links Records to, whose own Records were not sent."""
    unsent = {c["id"] for c in candidates if c["kind"] == "tag" and not c.get("records_sent")}
    linked = {
        link["to"]["id"]
        for rec in records
        for link in rec.get("links", [])
        if link["type"] == "belongs_to" and "id" in link["to"]
    }
    return sorted(linked & unsent)


def _tag_list(conn: sqlite3.Connection, workspace: str) -> list[dict[str, Any]]:
    return [
        {"id": record_id, "kind": "tag", "title": title, "records_sent": False}
        for record_id, title in conn.execute(
            "SELECT id, title FROM records WHERE workspace = ? AND kind = 'tag'"
            " AND lifecycle != 'superseded' ORDER BY id",
            (workspace,),
        )
    ]


def _same_conversation(conn: sqlite3.Connection, workspace: str, unit: Unit) -> set[int]:
    """Tags of Records citing another item of the conversation, session or recording of this
    unit."""
    prefixes = {loc.partition("/")[0] + "/" for loc in unit.locators}
    found: set[int] = set()
    for prefix in prefixes:
        rows = conn.execute(
            "SELECT r.id, r.kind FROM records r JOIN evidence e ON e.record_id = r.id"
            " WHERE r.workspace = ? AND substr(e.locator, 1, ?) = ?",
            (workspace, len(prefix), prefix),
        ).fetchall()
        for record_id, kind in rows:
            if kind == "tag":
                found.add(record_id)
            else:
                found.update(
                    to_id
                    for (to_id,) in conn.execute(
                        "SELECT to_id FROM links WHERE type = 'belongs_to'"
                        " AND from_type = 'record' AND from_id = ? AND to_type = 'record'",
                        (record_id,),
                    )
                )
    return found


def _named_in(conn: sqlite3.Connection, workspace: str, unit: Unit) -> set[int]:
    text = key(unit.text)
    return {
        record_id
        for record_id, known in tags.names(conn, workspace).items()
        if any(key(name) in text for name in known)
    }


def _records_of(
    conn: sqlite3.Connection, workspace: str, tag_id: int, stale_days: int
) -> list[dict[str, Any]]:
    cutoff = (datetime.now(UTC) - timedelta(days=stale_days)).isoformat()
    marks = ", ".join("?" for _ in _OPEN)
    return [
        {
            "id": record_id,
            "kind": kind,
            "title": title,
            "lifecycle": lifecycle,
            "tag": tag_id,
        }
        for record_id, kind, title, lifecycle in conn.execute(
            "SELECT r.id, r.kind, r.title, r.lifecycle FROM records r"
            " JOIN links l ON l.from_type = 'record'"
            " AND l.from_id = r.id AND l.type = 'belongs_to' AND l.to_type = 'record'"
            " AND l.to_id = ?"
            f" WHERE r.workspace = ? AND (r.lifecycle IN ({marks}) OR r.updated_at >= ?)"
            " ORDER BY r.updated_at DESC, r.id",
            (tag_id, workspace, *_OPEN, cutoff),
        )
    ]
