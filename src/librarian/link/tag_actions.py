"""What a person does to a tag: confirm, rename, merge, split, move a Record.

Each is a Person event on a Record, and the importer never undoes it: a merged tag's names
become Aliases of the survivor, so the old name resolves there, and the importer itself only ever
suggests a merge."""

import sqlite3

from librarian import events
from librarian.clock import utc_now_iso
from librarian.link import review, tags
from librarian.link.errors import Invalid

BELONGS_TO = "type = 'belongs_to' AND from_type = 'record' AND to_type = 'record'"


def _need_tag(conn: sqlite3.Connection, workspace: str, tag_id: int) -> str:
    row = conn.execute(
        "SELECT title, lifecycle FROM records WHERE workspace = ? AND id = ? AND kind = 'tag'",
        (workspace, tag_id),
    ).fetchone()
    if row is None:
        raise Invalid(404, f"no tag {tag_id}")
    if row[1] == "superseded":
        raise Invalid(409, f"tag {tag_id} was merged into another")
    return row[0]


def _need_free_name(conn: sqlite3.Connection, workspace: str, name: str, owner: int | None) -> str:
    name = name.strip()
    if not name:
        raise Invalid(400, "name must not be empty")
    taken = tags.match(conn, workspace, name)
    if taken.ambiguous or (taken.exact is not None and taken.exact != owner):
        raise Invalid(409, f"another tag is already called {name!r}")
    return name


def _settle(conn: sqlite3.Connection, workspace: str, tag_id: int) -> None:
    conn.execute(
        "UPDATE review_entries SET resolved_at = ?, resolution = 'accepted'"
        " WHERE workspace = ? AND resolved_at IS NULL"
        " AND kind IN (?, ?, ?) AND ? IN (record_id, COALESCE(other_record_id, record_id))",
        (
            utc_now_iso(),
            workspace,
            review.INFERRED_TAG,
            review.SUGGESTED_TAG,
            review.MERGE_TAG,
            tag_id,
        ),
    )


def _alias(conn: sqlite3.Connection, workspace: str, tag_id: int, alias: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO tag_aliases (workspace, record_id, alias) VALUES (?, ?, ?)",
        (workspace, tag_id, alias),
    )


def confirm(conn: sqlite3.Connection, workspace: str, tag_id: int) -> int:
    _need_tag(conn, workspace, tag_id)
    conn.execute("UPDATE records SET basis = 'confirmed' WHERE id = ?", (tag_id,))
    conn.execute(
        "UPDATE review_entries SET resolved_at = ?, resolution = 'accepted'"
        " WHERE workspace = ? AND kind = ? AND record_id = ? AND resolved_at IS NULL",
        (utc_now_iso(), workspace, review.INFERRED_TAG, tag_id),
    )
    events.append(conn, workspace, tag_id, "confirm")
    return tag_id


def rename(conn: sqlite3.Connection, workspace: str, tag_id: int, name: str) -> int:
    """The old title stays as an Alias, so the old name still reaches the tag."""
    old = _need_tag(conn, workspace, tag_id)
    name = _need_free_name(conn, workspace, name, tag_id)
    _alias(conn, workspace, tag_id, old)
    conn.execute(
        "UPDATE records SET title = ?, basis = 'confirmed', updated_at = ? WHERE id = ?",
        (name, utc_now_iso(), tag_id),
    )
    events.append(conn, workspace, tag_id, "rename", {"from": old, "to": name})
    return tag_id


def merge(conn: sqlite3.Connection, workspace: str, tag_id: int, into: int) -> int:
    """`tag_id` goes into `into`: its Records, its title and its Aliases become the
    survivor's."""
    if tag_id == into:
        raise Invalid(400, "a tag cannot be merged into itself")
    title = _need_tag(conn, workspace, tag_id)
    _need_tag(conn, workspace, into)
    aliases = [
        a
        for (a,) in conn.execute(
            "SELECT alias FROM tag_aliases WHERE workspace = ? AND record_id = ?",
            (workspace, tag_id),
        )
    ]
    conn.execute(
        "DELETE FROM tag_aliases WHERE workspace = ? AND record_id = ?", (workspace, tag_id)
    )
    for alias in [title, *aliases]:
        _alias(conn, workspace, into, alias)
    conn.execute(
        f"UPDATE OR IGNORE links SET to_id = ? WHERE workspace = ? AND {BELONGS_TO} AND to_id = ?",
        (into, workspace, tag_id),
    )
    conn.execute(
        f"DELETE FROM links WHERE workspace = ? AND {BELONGS_TO} AND to_id = ?",
        (workspace, tag_id),
    )
    conn.execute(
        "UPDATE records SET parent_id = ? WHERE workspace = ? AND parent_id = ? AND id != ?",
        (into, workspace, tag_id, into),
    )
    conn.execute(
        "UPDATE records SET lifecycle = 'superseded', updated_at = ? WHERE id = ?",
        (utc_now_iso(), tag_id),
    )
    _settle(conn, workspace, tag_id)
    events.append(conn, workspace, tag_id, "merge", {"into": into, "lifecycle": "superseded"})
    events.append(conn, workspace, into, "merge", {"from": tag_id})
    return into


def _member(conn: sqlite3.Connection, workspace: str, record_id: int, tag_id: int) -> bool:
    return bool(
        conn.execute(
            f"SELECT 1 FROM links WHERE workspace = ? AND {BELONGS_TO}"
            " AND from_id = ? AND to_id = ?",
            (workspace, record_id, tag_id),
        ).fetchone()
    )


def move(conn: sqlite3.Connection, workspace: str, record_id: int, tag_id: int) -> None:
    """The Record belongs to `tag_id` alone; extraction does not link it back (see `moved`)."""
    _need_tag(conn, workspace, tag_id)
    conn.execute(
        f"DELETE FROM links WHERE workspace = ? AND {BELONGS_TO} AND from_id = ?",
        (workspace, record_id),
    )
    conn.execute(
        "INSERT INTO links (workspace, type, from_type, from_id, to_type, to_id, created_at)"
        " VALUES (?, 'belongs_to', 'record', ?, 'record', ?, ?)",
        (workspace, record_id, tag_id, utc_now_iso()),
    )
    events.append(conn, workspace, record_id, "tag_move", {"tag_id": tag_id})


def moved(conn: sqlite3.Connection, workspace: str, record_id: int) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM record_events"
            " WHERE workspace = ? AND record_id = ? AND event = 'tag_move'",
            (workspace, record_id),
        ).fetchone()
    )


def split(
    conn: sqlite3.Connection, workspace: str, tag_id: int, name: str, record_ids: list[int]
) -> int:
    """A new tag named `name` takes `record_ids`, which must belong to this one. Returns its
    id."""
    _need_tag(conn, workspace, tag_id)
    name = _need_free_name(conn, workspace, name, None)
    if not record_ids:
        raise Invalid(400, "record_ids must name the Records that leave")
    for record_id in record_ids:
        if not _member(conn, workspace, record_id, tag_id):
            raise Invalid(404, f"Record {record_id} does not belong to tag {tag_id}")
    now = utc_now_iso()
    new = conn.execute(
        "INSERT INTO records (workspace, kind, title, lifecycle, basis, created_at, updated_at)"
        " VALUES (?, 'tag', ?, 'open', 'confirmed', ?, ?)",
        (workspace, name, now, now),
    ).lastrowid
    for record_id in record_ids:
        move(conn, workspace, record_id, new)
    events.append(conn, workspace, tag_id, "split", {"new_tag_id": new, "record_ids": record_ids})
    return new
