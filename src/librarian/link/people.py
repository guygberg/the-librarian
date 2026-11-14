"""People: Slack ids link automatically; text names link only on an exact, unique Alias match."""

import json
import sqlite3
from typing import Any

from librarian import config
from librarian.clock import utc_now_iso
from librarian.link import review
from librarian.link.names import key

SLACK = "slack:"


def aliases_for(conn: sqlite3.Connection, workspace: str, person_id: int) -> list[str]:
    row = conn.execute(
        "SELECT aliases, slack_id FROM people WHERE workspace = ? AND id = ?",
        (workspace, person_id),
    ).fetchone()
    return ([SLACK + row[1]] if row and row[1] else []) + (json.loads(row[0]) if row else [])


def alias_rows(conn: sqlite3.Connection, workspace: str) -> list[tuple[int, str]]:
    return [
        (pid, alias)
        for pid, aliases, slack_id in conn.execute(
            "SELECT id, aliases, slack_id FROM people WHERE workspace = ? ORDER BY id", (workspace,)
        )
        for alias in (([SLACK + slack_id] if slack_id else []) + json.loads(aliases))
    ]


def add_alias(conn: sqlite3.Connection, workspace: str, person_id: int, alias: str) -> None:
    if alias in aliases_for(conn, workspace, person_id):
        return
    if alias.startswith(SLACK):
        changed = conn.execute(
            "UPDATE people SET slack_id = ? WHERE workspace = ? AND id = ? AND slack_id IS NULL",
            (alias.removeprefix(SLACK), workspace, person_id),
        ).rowcount
        if changed:
            return
    conn.execute(
        "UPDATE people SET aliases = json_insert(aliases, '$[#]', ?)"
        " WHERE workspace = ? AND id = ?",
        (alias, workspace, person_id),
    )


def remove_alias(conn: sqlite3.Connection, workspace: str, person_id: int, alias: str) -> None:
    conn.execute(
        "UPDATE people SET slack_id = NULL WHERE workspace = ? AND id = ? AND slack_id = ?",
        (workspace, person_id, alias.removeprefix(SLACK) if alias.startswith(SLACK) else None),
    )
    conn.execute(
        "UPDATE people SET aliases = (SELECT json_group_array(value)"
        " FROM json_each(people.aliases) WHERE value != ?) WHERE workspace = ? AND id = ?",
        (alias, workspace, person_id),
    )


def new_person(conn: sqlite3.Connection, workspace: str, name: str, is_me: bool = False) -> int:
    return conn.execute(
        "INSERT INTO people (workspace, name, created_at, is_me) VALUES (?, ?, ?, ?)",
        (workspace, name, utc_now_iso(), is_me),
    ).lastrowid


def _by_slack_id(conn: sqlite3.Connection, workspace: str, slack_id: str) -> int | None:
    ids = {pid for pid, alias in alias_rows(conn, workspace) if alias == SLACK + slack_id}
    return ids.pop() if len(ids) == 1 else None


def save_slack_users(
    conn: sqlite3.Connection, workspace: str, users: list[dict[str, Any]], login_id: str | None
) -> None:
    """A Person per Slack user, the Slack id and the names as Aliases; the login's user is Me."""
    for user in users:
        profile = user.get("profile") or {}
        person_id = _by_slack_id(conn, workspace, user["id"])
        if person_id is None:
            name = (
                profile.get("real_name") or user.get("real_name") or user.get("name") or user["id"]
            )
            person_id = new_person(conn, workspace, name)
            for alias in (
                SLACK + user["id"],
                user.get("real_name"),
                user.get("name"),
                profile.get("real_name"),
                profile.get("display_name"),
            ):
                if alias:
                    add_alias(conn, workspace, person_id, alias)
        # Fill missing profile fields without overwriting the user's own corrections.
        conn.execute(
            "UPDATE people SET email = COALESCE(NULLIF(email, ''), ?),"
            " role = COALESCE(NULLIF(role, ''), ?),"
            " department = COALESCE(NULLIF(department, ''), ?) WHERE workspace = ? AND id = ?",
            (
                profile.get("email") or None,
                profile.get("title") or None,
                profile.get("department") or user.get("department") or None,
                workspace,
                person_id,
            ),
        )
        if user["id"] == login_id:
            _become_me(conn, workspace, person_id)


def _become_me(conn: sqlite3.Connection, workspace: str, person_id: int) -> None:
    """Me is a single Person: an earlier placeholder "Me" folds into the Slack login's Person."""
    old = conn.execute(
        "SELECT id FROM people WHERE workspace = ? AND is_me = 1 AND id != ?",
        (workspace, person_id),
    ).fetchall()
    conn.execute("UPDATE people SET is_me = 1 WHERE id = ?", (person_id,))
    for (old_id,) in old:
        for alias in aliases_for(conn, workspace, old_id):
            remove_alias(conn, workspace, old_id, alias)
            add_alias(conn, workspace, person_id, alias)
        conn.execute(
            "UPDATE items SET owner_person_id = ? WHERE owner_person_id = ?", (person_id, old_id)
        )
        conn.execute(
            "UPDATE links SET to_id = ? WHERE to_type = 'person' AND to_id = ?", (person_id, old_id)
        )
        conn.execute("UPDATE people SET is_me = 0 WHERE id = ?", (old_id,))


def me(conn: sqlite3.Connection, workspace: str) -> int:
    """The Me Person, with the names listed at setup as its Aliases."""
    row = conn.execute(
        "SELECT id FROM people WHERE workspace = ? AND is_me = 1", (workspace,)
    ).fetchone()
    person_id = row[0] if row else new_person(conn, workspace, "Me", is_me=True)
    for name in config.load().get("me_names", []):
        add_alias(conn, workspace, person_id, name)
    return person_id


def _by_name(conn: sqlite3.Connection, workspace: str, name: str) -> int | None:
    """The one Person whose Alias is this name, or None when no Person or several have it."""
    wanted = key(name)
    found = {
        person_id
        for person_id, alias in alias_rows(conn, workspace)
        if not alias.startswith(SLACK) and key(alias) == wanted
    }
    return found.pop() if len(found) == 1 else None


def resolve(
    conn: sqlite3.Connection, workspace: str, end: dict[str, str], recording: bool
) -> tuple[int | None, str | None]:
    """(person id, None) when the end is certain, else (None, the review kind): a name that is not
    one known Alias, or a first-person line of a recording, whose speaker nobody has set."""
    ((kind, value),) = end.items()
    if kind == "slack_user":
        person_id = _by_slack_id(conn, workspace, value)
        if person_id is None:  # not in the users list: still a stable Person, keyed by its id
            person_id = new_person(conn, workspace, value)
            add_alias(conn, workspace, person_id, SLACK + value)
        return person_id, None
    if kind == "speaker":
        return (None, review.UNKNOWN_SPEAKER) if recording else (me(conn, workspace), None)
    me(conn, workspace)  # the names listed at setup are Aliases of Me before the lookup
    person_id = _by_name(conn, workspace, value)
    return (person_id, None) if person_id is not None else (None, review.UNCONFIRMED_PERSON)
