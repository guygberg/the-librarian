"""`librarian project <name>`: resolve one project only when one match is clearly ahead, then report its facts."""

import sqlite3
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from librarian import config
from librarian.link import projects
from librarian.query import core, envelope, stale

NOT_FOUND = "not found"
MIN_SCORE = 0.6
WORD_MATCH = 0.9  # the name contains every word asked for: "payments" finds "Payments migration"


def _score(wanted: str, name: str) -> float:
    have, words = projects.key(name), set(projects.key(name).split())
    if have == wanted:
        return 1.0
    if set(wanted.split()) <= words:
        return WORD_MATCH
    return SequenceMatcher(None, have, wanted).ratio()


def _member_ids(conn: sqlite3.Connection, workspace: str, project_id: int) -> list[int]:
    return [
        row[0]
        for row in conn.execute(
            "SELECT from_id FROM links WHERE workspace = ? AND type = 'belongs_to' AND from_type = 'record'"
            " AND to_type = 'record' AND to_id = ? ORDER BY from_id",
            (workspace, project_id),
        )
    ]


def _last_activity(conn: sqlite3.Connection, workspace: str, ids: list[int]) -> str | None:
    marks = ", ".join("?" * len(ids))
    times = [
        stale.evidence_time(loc, retrieved)
        for loc, retrieved in conn.execute(
            f"SELECT locator, retrieved_at FROM evidence WHERE workspace = ? AND record_id IN ({marks})",
            (workspace, *ids),
        )
    ]
    return max(times).isoformat() if times else None


def _candidate(conn: sqlite3.Connection, workspace: str, project_id: int) -> dict[str, Any]:
    title, parent_id = conn.execute("SELECT title, parent_id FROM records WHERE id = ?", (project_id,)).fetchone()
    parent = conn.execute("SELECT title FROM records WHERE id = ?", (parent_id,)).fetchone() if parent_id else None
    ids = [project_id, *_member_ids(conn, workspace, project_id)]
    return {
        "id": project_id,
        "name": title,
        "parent": parent[0] if parent else None,
        "last_activity": _last_activity(conn, workspace, ids),
    }


def resolve(conn: sqlite3.Connection, workspace: str, name: str) -> tuple[int | None, list[int]]:
    """(winner or None, every candidate best first). An exact name or Alias wins alone; otherwise the winner is
    the only candidate worth considering."""
    wanted = projects.key(name)
    scores = {
        project_id: max(_score(wanted, n) for n in known) for project_id, known in projects.names(conn, workspace).items()
    }
    ranked = sorted((pid for pid, s in scores.items() if s >= MIN_SCORE), key=lambda pid: (-scores[pid], pid))
    exact = [pid for pid in ranked if scores[pid] == 1.0]
    if len(exact) == 1:
        return exact[0], ranked
    if len(ranked) == 1:
        return ranked[0], ranked
    return None, ranked


def _cite(view: dict[str, Any]) -> list[str]:
    return [e["locator"] for e in view.get("evidence", [])]


def _fact(view: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return {"record_id": view["id"], **fields, "evidence": _cite(view)}


def _owner(view: dict[str, Any]) -> str | None:
    """An action item's owner field, or the person a blocker's owner Link points at."""
    return view.get("owner") or next((link["to"] for link in view["links"] if link["type"] == "owner"), None)


def _latest(views: list[dict[str, Any]]) -> dict[str, Any] | None:
    return max(views, key=lambda v: v.get("last_evidence", ""), default=None)


def facts(project: dict[str, Any], members: list[dict[str, Any]]) -> dict[str, Any]:
    """Status, owners, deadlines, latest decision and main blocker, each with its Evidence locators or "not found"."""
    unfinished = [v for v in members if v["lifecycle"] in stale.UNFINISHED and v["kind"] in ("action_item", "blocker")]
    owners: dict[str, list[dict[str, Any]]] = {}
    for view in unfinished:
        if name := _owner(view):
            owners.setdefault(name, []).append(view)
    deadlines = [v for v in members if v.get("stated_deadline")]
    decision = _latest([v for v in members if v["kind"] == "decision"])
    blocker = _latest([v for v in unfinished if v["kind"] == "blocker"])
    return {
        "status": _fact(project, value=project["lifecycle"]),
        "owners": [
            {"name": name, "records": [v["id"] for v in views], "evidence": [loc for v in views for loc in _cite(v)]}
            for name, views in owners.items()
        ]
        or NOT_FOUND,
        "deadlines": [_fact(v, title=v["title"], deadline=v["stated_deadline"]) for v in deadlines] or NOT_FOUND,
        "latest_decision": _fact(decision, title=decision["title"]) if decision else NOT_FOUND,
        "main_blocker": _fact(blocker, title=blocker["title"]) if blocker else NOT_FOUND,
    }


def project(conn: sqlite3.Connection, workspace: str, name: str, at: datetime | None = None) -> dict[str, Any]:
    at = at or core.now()
    cfg = config.load()
    winner, ranked = resolve(conn, workspace, name)
    if winner is None:
        found = [_candidate(conn, workspace, pid) for pid in ranked]
        warning = {
            "code": "project_ambiguous" if found else "project_not_found",
            "message": f"which project is meant by {name!r}?" if found else f"no project matches {name!r}",
        }
        answer = envelope.build(
            conn, workspace, cfg, [], at=at, resolved={"project": None, "baseline": None}, candidates=found, project=NOT_FOUND
        )
        answer["warnings"].insert(0, warning)
        return answer
    views = [core.current_view(conn, workspace, rid, cfg, at) for rid in [winner, *_member_ids(conn, workspace, winner)]]
    resolved = {"project": {"id": winner, "name": views[0]["title"]}, "baseline": None}
    return envelope.build(conn, workspace, cfg, views, at=at, resolved=resolved, project=facts(views[0], views[1:]))
