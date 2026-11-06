"""Projects: an exact name or Alias links automatically; a near name is only suggested; nothing is merged."""

import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher

NEAR_RATIO = 0.85  # "Atlas Migration" vs "Atlas Migrations" is near; "Atlas" vs "Apollo" is not


def key(name: str) -> str:
    """Case and spacing differences are not a different name; anything further apart is."""
    return " ".join(name.casefold().split())


@dataclass(frozen=True)
class Match:
    exact: int | None = None  # the one project with this name or Alias
    ambiguous: bool = False  # several projects have it: never auto-links
    near: tuple[int, ...] = ()  # projects with a similar, not equal, name


def names(conn: sqlite3.Connection, workspace: str) -> dict[int, list[str]]:
    """Every project with its title and Aliases; a merged one is gone, its names are the survivor's Aliases."""
    found: dict[int, list[str]] = {
        record_id: [title]
        for record_id, title in conn.execute(
            "SELECT id, title FROM records WHERE workspace = ? AND kind = 'project' AND lifecycle != 'superseded'", (workspace,)
        )
    }
    for record_id, alias in conn.execute("SELECT record_id, alias FROM project_aliases WHERE workspace = ?", (workspace,)):
        found.setdefault(record_id, []).append(alias)
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
