"""Read side of Records: one Record with its owner, project links and Evidence."""

import sqlite3
from typing import Any

from librarian import store
from librarian.link import review

_FIELDS = (
    "id",
    "kind",
    "title",
    "body",
    "lifecycle",
    "basis",
    "commitment",
    "stated_deadline",
    "reasoning",
)


def get(conn: sqlite3.Connection, workspace: str, record_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        f"SELECT {', '.join(_FIELDS)}, parent_id, owner_person_id FROM records"
        " WHERE workspace = ? AND id = ?",
        (workspace, record_id),
    ).fetchone()
    if row is None:
        return None
    record: dict[str, Any] = {
        k: v for k, v in zip(_FIELDS, row, strict=False) if v not in (None, "")
    }
    parent_id, owner_id = row[-2:]
    if owner_id:
        name, is_me = conn.execute(
            "SELECT name, is_me FROM persons WHERE id = ?", (owner_id,)
        ).fetchone()
        record["owner"] = name
        if is_me:
            record["owner_is_me"] = True
    # Suggested links: shown with their mark, never as the Record's owner or Links.
    suggested = review.for_record(conn, workspace, record_id)
    if suggested:
        record["suggested"] = suggested
        if any(s["kind"] == review.UNKNOWN_SPEAKER and s["link"] == "owner" for s in suggested):
            record["owner"] = review.MARKS[review.UNKNOWN_SPEAKER]
    links = [
        {"type": type_, "to_type": to_type, "to_id": to_id, "to": _label(conn, to_type, to_id)}
        for type_, to_type, to_id in conn.execute(
            "SELECT type, to_type, to_id FROM links"
            " WHERE workspace = ? AND from_type = 'record' AND from_id = ?"
            " ORDER BY id",
            (workspace, record_id),
        )
    ]
    record["projects"] = [
        {"id": link["to_id"], "title": link["to"]} for link in links if link["type"] == "belongs_to"
    ]
    if parent_id:
        record["parent"] = {"id": parent_id, "title": _label(conn, "record", parent_id)}
    record["links"] = [link for link in links if link["type"] != "belongs_to"]
    gone = store.gone_ids(conn, workspace, "slack")
    record["evidence"] = [
        {
            "locator": loc,
            "quote": quote,
            "role": role,
            **({"gloss": gloss} if gloss else {}),
            **({"gone_from_source": True} if store.evidence_is_gone(loc, gone) else {}),
        }
        for loc, quote, role, gloss in conn.execute(
            "SELECT locator, quote, role, gloss FROM evidence"
            " WHERE workspace = ? AND record_id = ? ORDER BY id",
            (workspace, record_id),
        )
    ]
    return record


def _label(conn: sqlite3.Connection, to_type: str, to_id: int) -> str | None:
    table, column = {"record": ("records", "title"), "person": ("persons", "name")}.get(
        to_type, (None, None)
    )
    if table is None:
        return None
    row = conn.execute(f"SELECT {column} FROM {table} WHERE id = ?", (to_id,)).fetchone()
    return row[0] if row else None
