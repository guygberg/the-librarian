"""What a person does to a project: confirm, rename, merge, split, move a Record.

Each is a Person event on a Record, and the importer never undoes it: a merged project's names become Aliases of the
survivor, so the old name resolves there, and the importer itself only ever suggests a merge."""

import sqlite3
from datetime import UTC, datetime

from librarian import events
from librarian.link import projects, review
from librarian.link.review_actions import Invalid

BELONGS_TO = "type = 'belongs_to' AND from_type = 'record' AND to_type = 'record'"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _need_project(conn: sqlite3.Connection, workspace: str, project_id: int) -> str:
    row = conn.execute(
        "SELECT title, lifecycle FROM records WHERE workspace = ? AND id = ? AND kind = 'project'", (workspace, project_id)
    ).fetchone()
    if row is None:
        raise Invalid(404, f"no project {project_id}")
    if row[1] == "superseded":
        raise Invalid(409, f"project {project_id} was merged into another")
    return row[0]


def _need_free_name(conn: sqlite3.Connection, workspace: str, name: str, owner: int | None) -> str:
    name = name.strip()
    if not name:
        raise Invalid(400, "name must not be empty")
    taken = projects.match(conn, workspace, name)
    if taken.ambiguous or (taken.exact is not None and taken.exact != owner):
        raise Invalid(409, f"another project is already called {name!r}")
    return name


def _settle(conn: sqlite3.Connection, workspace: str, project_id: int) -> None:
    conn.execute(
        "UPDATE review_entries SET resolved_at = ?, resolution = 'accepted' WHERE workspace = ? AND resolved_at IS NULL"
        " AND kind IN (?, ?, ?) AND ? IN (record_id, COALESCE(other_record_id, record_id))",
        (_now(), workspace, review.INFERRED_PROJECT, review.SUGGESTED_PROJECT, review.MERGE_PROJECT, project_id),
    )


def _alias(conn: sqlite3.Connection, workspace: str, project_id: int, alias: str) -> None:
    conn.execute("INSERT OR IGNORE INTO project_aliases (workspace, record_id, alias) VALUES (?, ?, ?)", (workspace, project_id, alias))


def confirm(conn: sqlite3.Connection, workspace: str, project_id: int) -> int:
    _need_project(conn, workspace, project_id)
    conn.execute("UPDATE records SET basis = 'confirmed' WHERE id = ?", (project_id,))
    conn.execute(
        "UPDATE review_entries SET resolved_at = ?, resolution = 'accepted'"
        " WHERE workspace = ? AND kind = ? AND record_id = ? AND resolved_at IS NULL",
        (_now(), workspace, review.INFERRED_PROJECT, project_id),
    )
    events.append(conn, workspace, project_id, "confirm")
    return project_id


def rename(conn: sqlite3.Connection, workspace: str, project_id: int, name: str) -> int:
    """The old title stays as an Alias, so the old name still reaches the project."""
    old = _need_project(conn, workspace, project_id)
    name = _need_free_name(conn, workspace, name, project_id)
    _alias(conn, workspace, project_id, old)
    conn.execute("UPDATE records SET title = ?, basis = 'confirmed', updated_at = ? WHERE id = ?", (name, _now(), project_id))
    events.append(conn, workspace, project_id, "rename", {"from": old, "to": name})
    return project_id


def merge(conn: sqlite3.Connection, workspace: str, project_id: int, into: int) -> int:
    """`project_id` goes into `into`: its Records, its title and its Aliases become the survivor's."""
    if project_id == into:
        raise Invalid(400, "a project cannot be merged into itself")
    title = _need_project(conn, workspace, project_id)
    _need_project(conn, workspace, into)
    aliases = [a for (a,) in conn.execute("SELECT alias FROM project_aliases WHERE workspace = ? AND record_id = ?", (workspace, project_id))]
    conn.execute("DELETE FROM project_aliases WHERE workspace = ? AND record_id = ?", (workspace, project_id))
    for alias in [title, *aliases]:
        _alias(conn, workspace, into, alias)
    conn.execute(f"UPDATE OR IGNORE links SET to_id = ? WHERE workspace = ? AND {BELONGS_TO} AND to_id = ?", (into, workspace, project_id))
    conn.execute(f"DELETE FROM links WHERE workspace = ? AND {BELONGS_TO} AND to_id = ?", (workspace, project_id))
    conn.execute("UPDATE records SET parent_id = ? WHERE workspace = ? AND parent_id = ? AND id != ?", (into, workspace, project_id, into))
    conn.execute("UPDATE records SET lifecycle = 'superseded', updated_at = ? WHERE id = ?", (_now(), project_id))
    _settle(conn, workspace, project_id)
    events.append(conn, workspace, project_id, "merge", {"into": into, "lifecycle": "superseded"})
    events.append(conn, workspace, into, "merge", {"from": project_id})
    return into


def _member(conn: sqlite3.Connection, workspace: str, record_id: int, project_id: int) -> bool:
    return bool(conn.execute(
        f"SELECT 1 FROM links WHERE workspace = ? AND {BELONGS_TO} AND from_id = ? AND to_id = ?", (workspace, record_id, project_id)
    ).fetchone())


def move(conn: sqlite3.Connection, workspace: str, record_id: int, project_id: int) -> None:
    """The Record belongs to `project_id` alone; extraction does not link it back (see `moved`)."""
    _need_project(conn, workspace, project_id)
    conn.execute(f"DELETE FROM links WHERE workspace = ? AND {BELONGS_TO} AND from_id = ?", (workspace, record_id))
    conn.execute(
        "INSERT INTO links (workspace, type, from_type, from_id, to_type, to_id, created_at)"
        " VALUES (?, 'belongs_to', 'record', ?, 'record', ?, ?)",
        (workspace, record_id, project_id, _now()),
    )
    events.append(conn, workspace, record_id, "project_move", {"project_id": project_id})


def moved(conn: sqlite3.Connection, workspace: str, record_id: int) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM record_events WHERE workspace = ? AND record_id = ? AND event = 'project_move'", (workspace, record_id)
    ).fetchone())


def split(conn: sqlite3.Connection, workspace: str, project_id: int, name: str, record_ids: list[int]) -> int:
    """A new project named `name` takes `record_ids`, which must belong to this one. Returns its id."""
    _need_project(conn, workspace, project_id)
    name = _need_free_name(conn, workspace, name, None)
    if not record_ids:
        raise Invalid(400, "record_ids must name the Records that leave")
    for record_id in record_ids:
        if not _member(conn, workspace, record_id, project_id):
            raise Invalid(404, f"Record {record_id} does not belong to project {project_id}")
    now = _now()
    new = conn.execute(
        "INSERT INTO records (workspace, kind, title, lifecycle, basis, created_at, updated_at)"
        " VALUES (?, 'project', ?, 'open', 'confirmed', ?, ?)",
        (workspace, name, now, now),
    ).lastrowid
    for record_id in record_ids:
        move(conn, workspace, record_id, new)
    events.append(conn, workspace, project_id, "split", {"new_project_id": new, "record_ids": record_ids})
    return new
