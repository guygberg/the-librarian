"""Store the Records the validator accepted, with their Links and Evidence, in one transaction."""

import sqlite3
from datetime import UTC, datetime
from typing import Any

from librarian import locator
from librarian.link import people, review


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
    person_id, review_kind = people.resolve(conn, workspace, owner, _from_recording(rec)) if owner else (None, None)
    record_id = conn.execute(
        "INSERT INTO records (workspace, kind, title, body, lifecycle, basis, commitment, owner_person_id,"
        " stated_deadline, reasoning, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            workspace, rec["kind"], rec["title"], rec.get("body", ""), rec["lifecycle"], rec["basis"],
            rec.get("commitment"), person_id, rec.get("stated_deadline"), rec.get("reasoning"), now, now,
        ),
    ).lastrowid
    if review_kind:
        review.add(conn, workspace, review_kind, record_id, "owner", owner.get("name"))
    return record_id


def _from_recording(rec: dict[str, Any]) -> bool:
    return any(locator.parse(ev["locator"]).source == "drive" for ev in rec["evidence"])


def _link_and_cite(conn: sqlite3.Connection, workspace: str, ids: dict[str, int], rec: dict[str, Any]) -> None:
    record_id = ids[rec["ref"]]
    if "parent" in rec:
        conn.execute("UPDATE records SET parent_id = ? WHERE id = ?", (_record_end(ids, rec["parent"]), record_id))
    for link in rec.get("links", []):
        end = link["to"]
        if "ref" in end or "id" in end:
            to_type, to_id = "record", _record_end(ids, end)
        else:
            to_type = "person"
            to_id, review_kind = people.resolve(conn, workspace, end, _from_recording(rec))
            if review_kind:
                review.add(conn, workspace, review_kind, record_id, link["type"], end.get("name"))
                continue
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
