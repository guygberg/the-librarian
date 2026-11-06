"""People: Slack ids link automatically; text names link only on an exact, unique Alias match."""

import sqlite3
from datetime import UTC, datetime
from typing import Any

from librarian import config
from librarian.link import review

SLACK = "slack:"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _key(name: str) -> str:
    """Case and spacing differences are not a different name; anything further apart is."""
    return " ".join(name.casefold().split())


def _add_alias(conn: sqlite3.Connection, workspace: str, person_id: int, alias: str) -> None:
    conn.execute("INSERT OR IGNORE INTO aliases (workspace, person_id, alias) VALUES (?, ?, ?)", (workspace, person_id, alias))


def _new_person(conn: sqlite3.Connection, workspace: str, name: str, is_me: bool = False) -> int:
    return conn.execute(
        "INSERT INTO persons (workspace, name, created_at, is_me) VALUES (?, ?, ?, ?)", (workspace, name, _now(), is_me)
    ).lastrowid


def _by_slack_id(conn: sqlite3.Connection, workspace: str, slack_id: str) -> int | None:
    row = conn.execute(
        "SELECT person_id FROM aliases WHERE workspace = ? AND alias = ?", (workspace, SLACK + slack_id)
    ).fetchone()
    return row[0] if row else None


def save_slack_users(conn: sqlite3.Connection, workspace: str, users: list[dict[str, Any]], login_id: str | None) -> None:
    """A Person per Slack user, the Slack id and the names as Aliases; the login's user is Me."""
    for user in users:
        person_id = _by_slack_id(conn, workspace, user["id"])
        if person_id is None:
            name = user.get("real_name") or user.get("name") or user["id"]
            person_id = _new_person(conn, workspace, name)
            for alias in (SLACK + user["id"], user.get("real_name"), user.get("name")):
                if alias:
                    _add_alias(conn, workspace, person_id, alias)
        if user["id"] == login_id:
            _become_me(conn, workspace, person_id)


def _become_me(conn: sqlite3.Connection, workspace: str, person_id: int) -> None:
    """Me is a single Person: an earlier placeholder "Me" folds into the Slack login's Person."""
    old = conn.execute(
        "SELECT id FROM persons WHERE workspace = ? AND is_me = 1 AND id != ?", (workspace, person_id)
    ).fetchall()
    conn.execute("UPDATE persons SET is_me = 1 WHERE id = ?", (person_id,))
    for (old_id,) in old:
        conn.execute("UPDATE OR IGNORE aliases SET person_id = ? WHERE person_id = ?", (person_id, old_id))
        conn.execute("DELETE FROM aliases WHERE person_id = ?", (old_id,))
        conn.execute("UPDATE records SET owner_person_id = ? WHERE owner_person_id = ?", (person_id, old_id))
        conn.execute("UPDATE links SET to_id = ? WHERE to_type = 'person' AND to_id = ?", (person_id, old_id))
        conn.execute("UPDATE persons SET is_me = 0 WHERE id = ?", (old_id,))


def me(conn: sqlite3.Connection, workspace: str) -> int:
    """The Me Person, with the names listed at setup as its Aliases."""
    row = conn.execute("SELECT id FROM persons WHERE workspace = ? AND is_me = 1", (workspace,)).fetchone()
    person_id = row[0] if row else _new_person(conn, workspace, "Me", is_me=True)
    for name in config.load().get("me_names", []):
        _add_alias(conn, workspace, person_id, name)
    return person_id


def _by_name(conn: sqlite3.Connection, workspace: str, name: str) -> int | None:
    """The one Person whose Alias is this name, or None when no Person or several have it."""
    wanted = _key(name)
    found = {
        person_id
        for person_id, alias in conn.execute("SELECT person_id, alias FROM aliases WHERE workspace = ?", (workspace,))
        if not alias.startswith(SLACK) and _key(alias) == wanted
    }
    return found.pop() if len(found) == 1 else None


def resolve(conn: sqlite3.Connection, workspace: str, end: dict[str, str], recording: bool) -> tuple[int | None, str | None]:
    """(person id, None) when the end is certain, else (None, the review kind): a name that is not one known
    Alias, or a first-person line of a recording, whose speaker nobody has set."""
    (kind, value), = end.items()
    if kind == "slack_user":
        person_id = _by_slack_id(conn, workspace, value)
        if person_id is None:  # not in the users list: still a stable Person, keyed by its id
            person_id = _new_person(conn, workspace, value)
            _add_alias(conn, workspace, person_id, SLACK + value)
        return person_id, None
    if kind == "speaker":
        return (None, review.UNKNOWN_SPEAKER) if recording else (me(conn, workspace), None)
    me(conn, workspace)  # the names listed at setup are Aliases of Me before the lookup
    person_id = _by_name(conn, workspace, value)
    return (person_id, None) if person_id is not None else (None, review.UNCONFIRMED_PERSON)
