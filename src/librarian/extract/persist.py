"""Store the Records the validator accepted, with their Links and Evidence, in one transaction."""

import sqlite3
from datetime import UTC, datetime
from typing import Any

from librarian import locator


def _now() -> str:
    return datetime.now(UTC).isoformat()


def persist(
    conn: sqlite3.Connection, workspace: str, unit_key: str, text_hash: str, records: list[dict[str, Any]]
) -> None:
    conn.execute("BEGIN")
    try:
        ids = {rec["ref"]: _insert_record(conn, workspace, rec) for rec in records}
        for rec in records:
            _link_and_cite(conn, workspace, ids, rec)
        conn.execute(
            "INSERT OR REPLACE INTO extracted_units (workspace, unit_key, text_hash, extracted_at) VALUES (?, ?, ?, ?)",
            (workspace, unit_key, text_hash, _now()),
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _insert_record(conn: sqlite3.Connection, workspace: str, rec: dict[str, Any]) -> int:
    now = _now()
    owner = rec.get("owner")
    return conn.execute(
        "INSERT INTO records (workspace, kind, title, body, lifecycle, basis, commitment, owner_person_id,"
        " stated_deadline, reasoning, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            workspace, rec["kind"], rec["title"], rec.get("body", ""), rec["lifecycle"], rec["basis"],
            rec.get("commitment"), _person(conn, workspace, owner) if owner else None,
            rec.get("stated_deadline"), rec.get("reasoning"), now, now,
        ),
    ).lastrowid


def _link_and_cite(conn: sqlite3.Connection, workspace: str, ids: dict[str, int], rec: dict[str, Any]) -> None:
    record_id = ids[rec["ref"]]
    if "parent" in rec:
        conn.execute("UPDATE records SET parent_id = ? WHERE id = ?", (_record_end(ids, rec["parent"]), record_id))
    for link in rec.get("links", []):
        end = link["to"]
        to_type, to_id = ("record", _record_end(ids, end)) if ("ref" in end or "id" in end) else (
            "person", _person(conn, workspace, end))
        conn.execute(
            "INSERT OR IGNORE INTO links (workspace, type, from_type, from_id, to_type, to_id, created_at)"
            " VALUES (?, ?, 'record', ?, ?, ?, ?)",
            (workspace, link["type"], record_id, to_type, to_id, _now()),
        )
    for ev in rec["evidence"]:
        loc = locator.parse(ev["locator"])
        revision_id = conn.execute(
            "SELECT r.id FROM source_items i JOIN source_item_revisions r ON r.source_item_id = i.id"
            " WHERE i.workspace = ? AND i.source = ? AND i.stable_id = ? ORDER BY r.revision DESC LIMIT 1",
            (workspace, loc.source, loc.stable_id),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO evidence (workspace, record_id, revision_id, locator, quote, role, retrieved_at, gloss)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (workspace, record_id, revision_id, ev["locator"], ev["quote"], ev["role"], _now(), ev.get("gloss")),
        )


def _record_end(ids: dict[str, int], end: dict[str, Any]) -> int:
    return ids[end["ref"]] if "ref" in end else end["id"]


def _person(conn: sqlite3.Connection, workspace: str, end: dict[str, Any]) -> int:
    """The person for an owner or Link end; unseen ones are created, keyed by an alias of how they were named."""
    (kind, value), = end.items()
    alias = f"{kind}:{value}"
    name = "Me" if kind == "speaker" else value
    found = conn.execute("SELECT person_id FROM aliases WHERE workspace = ? AND alias = ?", (workspace, alias)).fetchone()
    if found:
        return found[0]
    person_id = conn.execute(
        "INSERT INTO persons (workspace, name, created_at) VALUES (?, ?, ?)", (workspace, name, _now())
    ).lastrowid
    conn.execute("INSERT INTO aliases (workspace, person_id, alias) VALUES (?, ?, ?)", (workspace, person_id, alias))
    return person_id
