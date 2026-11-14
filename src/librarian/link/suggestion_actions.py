"""Accept or reject a stored Suggestion. Analysis never writes domain objects; only these do, and
each is one transaction, so a refusal or failure leaves nothing behind.

A settled Suggestion answers a repeat with its settled result and writes nothing more."""

import json
import sqlite3
from typing import Any

from librarian import events
from librarian.clock import utc_now_iso
from librarian.link import people, review, tags
from librarian.link.errors import Invalid

_NEW_KIND = {"new_tag": "tag", "new_item": "action_item"}
_ENDS = {"record": "records", "person": "persons"}
_ROW = (
    "id, kind, link_type, payload, from_type, from_id, to_type, to_id, basis, status, resolved_at"
)


def _transaction(do):
    def run(conn: sqlite3.Connection, workspace: str, suggestion_id: int) -> dict[str, Any]:
        conn.execute("BEGIN IMMEDIATE")
        try:
            result = do(conn, workspace, suggestion_id)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        return result

    return run


def _load(conn, workspace: str, suggestion_id: int) -> dict[str, Any]:
    row = conn.execute(
        f"SELECT {_ROW} FROM suggestions WHERE workspace = ? AND id = ?", (workspace, suggestion_id)
    ).fetchone()
    if row is None:
        raise Invalid(404, f"no Suggestion {suggestion_id}")
    s = dict(zip(_ROW.split(", "), row, strict=True))
    s["payload"] = json.loads(s["payload"])
    return s


def _settled(conn, workspace: str, s: dict[str, Any], wanted: str) -> dict[str, Any] | None:
    """The result already recorded when `s` is settled the way `wanted` says; a refusal when it
    is settled the other way or superseded."""
    if s["status"] == "pending":
        return None
    if s["status"] != wanted:
        raise Invalid(409, f"this Suggestion is already {s['status']}")
    detail = json.loads(
        conn.execute(
            "SELECT detail FROM suggestion_events WHERE suggestion_id = ? AND event = ?"
            " ORDER BY id DESC LIMIT 1",
            (s["id"], wanted),
        ).fetchone()[0]
    )
    return {"id": s["id"], "status": wanted, "record_id": detail.get("record_id")}


def _settle(conn, workspace: str, s: dict[str, Any], status: str, record_id: int | None) -> None:
    now = utc_now_iso()
    conn.execute(
        "UPDATE suggestions SET status = ?, resolved_at = ? WHERE id = ? AND status = 'pending'",
        (status, now, s["id"]),
    )
    conn.execute(
        "INSERT INTO suggestion_events (workspace, suggestion_id, event, detail, at)"
        " VALUES (?, ?, ?, ?, ?)",
        (workspace, s["id"], status, json.dumps({"record_id": record_id}), now),
    )
    events.insert(
        conn,
        workspace,
        record_id,
        "accept_suggestion" if status == "accepted" else "reject_suggestion",
        {"suggestion": s["id"]},
        now,
    )


@_transaction
def reject(conn, workspace: str, suggestion_id: int) -> dict[str, Any]:
    s = _load(conn, workspace, suggestion_id)
    if done := _settled(conn, workspace, s, "rejected"):
        return done
    record_id = next(
        (s[f"{side}_id"] for side in ("from", "to") if s[f"{side}_type"] == "record"), None
    )
    _settle(conn, workspace, s, "rejected", record_id)
    return {"id": s["id"], "status": "rejected", "record_id": record_id}


@_transaction
def accept(conn, workspace: str, suggestion_id: int) -> dict[str, Any]:
    s = _load(conn, workspace, suggestion_id)
    if done := _settled(conn, workspace, s, "accepted"):
        return done
    if s["kind"] == "link":
        record_id = _accept_link(conn, workspace, s)
    else:
        record_id = _create_record(conn, workspace, s)
    _settle(conn, workspace, s, "accepted", record_id)
    return {"id": s["id"], "status": "accepted", "record_id": record_id}


def _create_record(conn, workspace: str, s: dict[str, Any]) -> int:
    p, now = s["payload"], utc_now_iso()
    kind = _NEW_KIND[s["kind"]]
    if kind == "tag" and tags.match(conn, workspace, p["title"]).exact is not None:
        raise Invalid(409, f"a Tag named {p['title']!r} already exists")
    owner_id, owner_name = _owner(conn, workspace, p.get("owner"))
    record_id = conn.execute(
        "INSERT INTO records (workspace, kind, title, body, lifecycle, basis, owner_person_id,"
        " stated_deadline, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            workspace,
            kind,
            p["title"],
            p.get("body", ""),
            p.get("lifecycle", "open"),
            s["basis"],
            owner_id,
            p.get("stated_deadline"),
            now,
            now,
        ),
    ).lastrowid
    if owner_name:  # the established Person-review path decides who this is
        review.add(conn, workspace, review.UNCONFIRMED_PERSON, record_id, "owner", owner_name)
    conn.execute(
        "INSERT INTO evidence (workspace, record_id, revision_id, locator, quote, role,"
        " retrieved_at) SELECT workspace, ?, revision_id, locator, quote, 'supports', ?"
        " FROM suggestion_evidence WHERE suggestion_id = ? ORDER BY id",
        (record_id, now, s["id"]),
    )
    # Without a unit it came from, the current view reports it as no longer found in sources.
    conn.execute(
        "INSERT INTO unit_records (workspace, unit_key, record_id) VALUES (?, ?, ?)",
        (workspace, f"suggestion:{s['id']}", record_id),
    )
    return record_id


def _owner(conn, workspace: str, owner: dict[str, Any] | None) -> tuple[int | None, str | None]:
    """(Person id, None) when known; (None, name) for a name nobody has confirmed."""
    if not owner:
        return None, None
    if "id" in owner:
        _need(conn, workspace, "person", owner["id"])
        return owner["id"], None
    person_id, review_kind = people.resolve(conn, workspace, {"name": owner["raw_name"]}, False)
    return (None, owner["raw_name"]) if review_kind else (person_id, None)


def _need(conn, workspace: str, end_type: str, end_id: int) -> None:
    found = conn.execute(
        f"SELECT 1 FROM {_ENDS[end_type]} WHERE workspace = ? AND id = ?", (workspace, end_id)
    ).fetchone()
    if not found:
        raise Invalid(409, f"the {end_type} {end_id} this Suggestion names is gone")


def _end(conn, workspace: str, s: dict[str, Any], side: str) -> tuple[str, int]:
    """One end of a Link, revalidated now: a candidate that still exists in this workspace, or
    the Record that accepting a new Tag/Item made."""
    if s[f"{side}_type"]:
        end = s[f"{side}_type"], s[f"{side}_id"]
        _need(conn, workspace, *end)
        return end
    named = s["payload"][side]
    row = conn.execute(
        "SELECT id FROM records WHERE workspace = ? AND kind = ? AND lower(title) = lower(?)"
        " AND lifecycle != 'superseded'",
        (workspace, _NEW_KIND[named["kind"]], named["title"]),
    ).fetchone()
    if row is None:
        raise Invalid(409, f"accept the new {_NEW_KIND[named['kind']]} {named['title']!r} first")
    return "record", row[0]


def _accept_link(conn, workspace: str, s: dict[str, Any]) -> int:
    from_end, to_end = _end(conn, workspace, s, "from"), _end(conn, workspace, s, "to")
    kind = s["link_type"]
    record_id = from_end[1] if from_end[0] == "record" else to_end[1]
    if kind == "owner":  # an owner is the Record's own column, not a Link row
        if not conn.execute(
            "UPDATE records SET owner_person_id = ?, updated_at = ?"
            " WHERE workspace = ? AND id = ? AND kind = 'action_item'",
            (to_end[1], utc_now_iso(), workspace, record_id),
        ).rowcount:
            raise Invalid(409, "only an Item has an owner")
        events.insert(
            conn,
            workspace,
            record_id,
            "owner_change",
            {"person_id": to_end[1], "suggestion": s["id"]},
        )
    else:
        conn.execute(
            "INSERT OR IGNORE INTO links"
            " (workspace, type, from_type, from_id, to_type, to_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (workspace, kind, *from_end, *to_end, utc_now_iso()),
        )
    return record_id
