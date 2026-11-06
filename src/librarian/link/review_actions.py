"""The Review list and what a person does to it: accept or reject a suggestion, move or split an Alias.

Every action appends a Person event to a Record; Aliases live in the `aliases` table, which Import never rewrites."""

import sqlite3
from datetime import UTC, datetime
from typing import Any

from librarian import events, records
from librarian.link import people, review


class Invalid(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


def rows(conn: sqlite3.Connection, workspace: str) -> dict[str, Any]:
    """Every open entry with both sides: the Record (with Evidence) and who or what the name might be."""
    out = []
    for entry in review.open_entries(conn, workspace):
        record = records.get(conn, workspace, entry["record_id"])
        row = {
            "id": entry["id"], "kind": entry["kind"], "mark": review.MARKS[entry["kind"]], "link": entry["link"],
            "raw_name": entry["raw_name"],
            "record": {k: record[k] for k in ("id", "kind", "title", "evidence")},
        }
        if entry["other_record_id"]:
            other = records.get(conn, workspace, entry["other_record_id"])
            row["other"] = {"id": other["id"], "kind": other["kind"], "title": other["title"]}
        elif entry["kind"] == review.UNCONFIRMED_PERSON:
            row["candidates"] = _candidates(conn, workspace, entry["raw_name"])
        out.append(row)
    return {"count": len(out), "rows": out}


def _candidates(conn: sqlite3.Connection, workspace: str, name: str) -> list[dict[str, Any]]:
    wanted = people.key(name)
    found = {
        pid: pname
        for pid, pname, alias in conn.execute(
            "SELECT p.id, p.name, a.alias FROM aliases a JOIN persons p ON p.id = a.person_id WHERE a.workspace = ?",
            (workspace,),
        )
        if not alias.startswith(people.SLACK) and people.key(alias) == wanted
    }
    return [{"id": pid, "name": pname} for pid, pname in found.items()]


def _entry(conn: sqlite3.Connection, workspace: str, entry_id: int) -> tuple[int, str, str, str | None]:
    row = conn.execute(
        "SELECT record_id, kind, link_type, raw_name FROM review_entries"
        " WHERE workspace = ? AND id = ? AND resolved_at IS NULL",
        (workspace, entry_id),
    ).fetchone()
    if row is None:
        raise Invalid(404, f"no open review entry {entry_id}")
    if row[1] != review.UNCONFIRMED_PERSON:
        raise Invalid(409, f"a {review.MARKS[row[1]]} is settled elsewhere")
    return row


def _settle(conn: sqlite3.Connection, entry_id: int, resolution: str) -> None:
    conn.execute(
        "UPDATE review_entries SET resolved_at = ?, resolution = ? WHERE id = ?",
        (datetime.now(UTC).isoformat(), resolution, entry_id),
    )


def accept(conn: sqlite3.Connection, workspace: str, entry_id: int, person_id: int | None) -> int:
    """The name becomes an Alias of `person_id` (a new Person named so when None) and of no one else, so that
    it links automatically next Import. Returns the Record it was suggested on."""
    record_id, _, link_type, raw_name = _entry(conn, workspace, entry_id)
    if person_id is None:
        person_id = people.new_person(conn, workspace, raw_name)
    else:
        _need_person(conn, workspace, person_id)
    wanted = people.key(raw_name)
    for alias_id, alias in conn.execute(
        "SELECT id, alias FROM aliases WHERE workspace = ? AND person_id != ?", (workspace, person_id)
    ).fetchall():
        if not alias.startswith(people.SLACK) and people.key(alias) == wanted:
            conn.execute("DELETE FROM aliases WHERE id = ?", (alias_id,))
    people.add_alias(conn, workspace, person_id, raw_name)
    if link_type != "owner":
        conn.execute(
            "INSERT OR IGNORE INTO links (workspace, type, from_type, from_id, to_type, to_id, created_at)"
            " VALUES (?, ?, 'record', ?, 'person', ?, ?)",
            (workspace, link_type, record_id, person_id, datetime.now(UTC).isoformat()),
        )
    _settle(conn, entry_id, "accepted")
    detail = {"alias": raw_name, "entry": entry_id}
    events.append(conn, workspace, record_id, "accept_suggestion", {**detail, "person_id": person_id} if link_type == "owner" else detail)
    return record_id


def reject(conn: sqlite3.Connection, workspace: str, entry_id: int) -> int:
    record_id, _, _, raw_name = _entry(conn, workspace, entry_id)
    _settle(conn, entry_id, "rejected")
    events.append(conn, workspace, record_id, "reject_suggestion", {"alias": raw_name, "entry": entry_id})
    return record_id


def _need_person(conn: sqlite3.Connection, workspace: str, person_id: int) -> None:
    if not conn.execute("SELECT 1 FROM persons WHERE workspace = ? AND id = ?", (workspace, person_id)).fetchone():
        raise Invalid(404, f"no person {person_id}")


def _need_alias(conn: sqlite3.Connection, workspace: str, person_id: int, alias: str) -> None:
    _need_person(conn, workspace, person_id)
    if not conn.execute(
        "SELECT 1 FROM aliases WHERE workspace = ? AND person_id = ? AND alias = ?", (workspace, person_id, alias)
    ).fetchone():
        raise Invalid(404, f"person {person_id} has no Alias {alias!r}")


def _need_record(conn: sqlite3.Connection, workspace: str, record_id: int) -> None:
    if not conn.execute("SELECT 1 FROM records WHERE workspace = ? AND id = ?", (workspace, record_id)).fetchone():
        raise Invalid(404, f"no Record {record_id}")


def move_alias(
    conn: sqlite3.Connection, workspace: str, alias: str, from_person: int, to_person: int, record_id: int
) -> None:
    """The Alias goes to another Person; `record_id` is the Record whose wrong link prompted it, and is re-owned."""
    _need_alias(conn, workspace, from_person, alias)
    _need_person(conn, workspace, to_person)
    _need_record(conn, workspace, record_id)
    conn.execute("DELETE FROM aliases WHERE workspace = ? AND person_id = ? AND alias = ?", (workspace, from_person, alias))
    people.add_alias(conn, workspace, to_person, alias)
    events.append(
        conn, workspace, record_id, "move_alias",
        {"alias": alias, "from_person_id": from_person, "person_id": to_person},
    )


def split_alias(
    conn: sqlite3.Connection, workspace: str, alias: str, from_person: int, record_id: int, name: str | None
) -> int:
    """The Alias leaves for a new Person (named `name`, else the Alias itself). Returns the new Person's id."""
    _need_alias(conn, workspace, from_person, alias)
    _need_record(conn, workspace, record_id)
    conn.execute("DELETE FROM aliases WHERE workspace = ? AND person_id = ? AND alias = ?", (workspace, from_person, alias))
    new = people.new_person(conn, workspace, name or alias)
    people.add_alias(conn, workspace, new, alias)
    events.append(
        conn, workspace, record_id, "split",
        {"alias": alias, "from_person_id": from_person, "person_id": new},
    )
    return new
