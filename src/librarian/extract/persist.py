"""Store the Records the validator accepted, with their Links and Evidence, in one transaction."""

import sqlite3
from datetime import UTC, datetime
from typing import Any

from librarian import locator
from librarian.link import people, projects, review


def _now() -> str:
    return datetime.now(UTC).isoformat()


def persist(
    conn: sqlite3.Connection, workspace: str, unit_key: str, text_hash: str, records: list[dict[str, Any]]
) -> None:
    conn.execute("BEGIN")
    try:
        near: dict[str, tuple[int, ...]] = {}  # ref of a new project -> existing projects with a near name
        ids = {rec["ref"]: _store_record(conn, workspace, rec, near) for rec in records}
        for rec in records:
            _link_and_cite(conn, workspace, ids, rec)
            _suggest_projects(conn, workspace, ids[rec["ref"]], rec, near)
        conn.execute("DELETE FROM unit_records WHERE workspace = ? AND unit_key = ?", (workspace, unit_key))
        conn.executemany(
            "INSERT OR IGNORE INTO unit_records (workspace, unit_key, record_id) VALUES (?, ?, ?)",
            [(workspace, unit_key, record_id) for record_id in ids.values()],
        )
        conn.execute(
            "INSERT OR REPLACE INTO extracted_units (workspace, unit_key, text_hash, extracted_at) VALUES (?, ?, ?, ?)",
            (workspace, unit_key, text_hash, _now()),
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _store_record(conn: sqlite3.Connection, workspace: str, rec: dict[str, Any], near: dict[str, tuple[int, ...]]) -> int:
    """The Record's id: the one Claude matched (same, updated), the one project with this exact name, or a new one."""
    decision = rec["match"]["decision"]
    if decision != "new":
        if decision == "updated":
            _update_record(conn, workspace, rec["match"]["id"], rec)
        return rec["match"]["id"]
    if rec["kind"] != "project":
        return _insert_record(conn, workspace, rec)
    found = projects.match(conn, workspace, rec["title"])
    if found.exact is not None:
        return found.exact
    # Never merged here: a second project is stored, inferred, and any near name is only suggested.
    record_id = _insert_record(conn, workspace, {**rec, "basis": "inferred"})
    review.add(conn, workspace, review.INFERRED_PROJECT, record_id, "project", rec["title"])
    if found.near:
        near[rec["ref"]] = found.near
        for other in found.near:
            review.add(conn, workspace, review.MERGE_PROJECT, record_id, "project", rec["title"], other)
    return record_id


def _suggest_projects(
    conn: sqlite3.Connection, workspace: str, record_id: int, rec: dict[str, Any], near: dict[str, tuple[int, ...]]
) -> None:
    """A Record of a new project with a near name might belong to the existing one: suggested, not linked."""
    for link in rec.get("links", []):
        for other in near.get(link["to"].get("ref"), ()) if link["type"] == "belongs_to" else ():
            title = conn.execute("SELECT title FROM records WHERE id = ?", (other,)).fetchone()[0]
            review.add(conn, workspace, review.SUGGESTED_PROJECT, record_id, "belongs_to", title, other)


def _update_record(conn: sqlite3.Connection, workspace: str, record_id: int, rec: dict[str, Any]) -> None:
    person_id, review_kind = _owner(conn, workspace, rec)
    conn.execute(
        "UPDATE records SET title = ?, body = ?, lifecycle = ?, basis = CASE WHEN basis = 'confirmed' THEN basis ELSE ? END,"
        " commitment = ?, owner_person_id = COALESCE(?, owner_person_id), stated_deadline = ?, reasoning = ?,"
        " updated_at = ? WHERE id = ?",
        (
            rec["title"], rec.get("body", ""), rec["lifecycle"], rec["basis"], rec.get("commitment"), person_id,
            rec.get("stated_deadline"), rec.get("reasoning"), _now(), record_id,
        ),
    )
    if review_kind:
        review.add(conn, workspace, review_kind, record_id, "owner", rec["owner"].get("name"))


def _owner(conn: sqlite3.Connection, workspace: str, rec: dict[str, Any]) -> tuple[int | None, str | None]:
    owner = rec.get("owner")
    return people.resolve(conn, workspace, owner, _from_recording(rec)) if owner else (None, None)


def _insert_record(conn: sqlite3.Connection, workspace: str, rec: dict[str, Any]) -> int:
    now = _now()
    owner = rec.get("owner")
    person_id, review_kind = _owner(conn, workspace, rec)
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
        if conn.execute(
            "SELECT 1 FROM evidence WHERE record_id = ? AND locator = ? AND quote = ?", (record_id, ev["locator"], ev["quote"])
        ).fetchone():
            continue  # a re-extraction cites the same span again
        conn.execute(
            "INSERT INTO evidence (workspace, record_id, revision_id, locator, quote, role, retrieved_at, gloss)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (workspace, record_id, revision_id, ev["locator"], ev["quote"], ev["role"], _now(), ev.get("gloss")),
        )


def _record_end(ids: dict[str, int], end: dict[str, Any]) -> int:
    return ids[end["ref"]] if "ref" in end else end["id"]
