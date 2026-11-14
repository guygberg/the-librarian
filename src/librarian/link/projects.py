"""Projects: an exact current name links automatically; a near name is only suggested; nothing
is merged."""

import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher

from librarian.link.names import key

NEAR_RATIO = 0.85  # "Atlas Migration" vs "Atlas Migrations" is near; "Atlas" vs "Apollo" is not


@dataclass(frozen=True)
class Match:
    exact: int | None = None  # the one project with this name
    ambiguous: bool = False  # several projects have it: never auto-links
    near: tuple[int, ...] = ()  # projects with a similar, not equal, name


def names(conn: sqlite3.Connection, workspace: str) -> dict[int, list[str]]:
    """Every active tag with its current title."""
    found: dict[int, list[str]] = {
        record_id: [title]
        for record_id, title in conn.execute(
            "SELECT id, title FROM items WHERE workspace = ? AND id IN (SELECT item_id FROM tags)"
            " AND lifecycle != 'superseded'",
            (workspace,),
        )
    }
    return found


def match(conn: sqlite3.Connection, workspace: str, title: str) -> Match:
    wanted = key(title)
    exact: set[int] = set()
    near: set[int] = set()
    for record_id, known in names(conn, workspace).items():
        for name in known:
            if key(name) == wanted:
                exact.add(record_id)
            elif SequenceMatcher(None, key(name), wanted).ratio() >= NEAR_RATIO:
                near.add(record_id)
    if len(exact) == 1:
        return Match(exact=exact.pop())
    if exact:
        return Match(ambiguous=True)
    return Match(near=tuple(sorted(near)))
