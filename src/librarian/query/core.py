"""The query core. `current_view` is the one place a Record's extracted state meets the person's events."""

import os
import sqlite3
import time
from datetime import UTC, datetime
from typing import Any

from librarian import events, records
from librarian.query import stale

# Kinds whose "done" must be earned: by completion Evidence or the person's mark (silence is not completion).
_EARNED_DONE = ("action_item", "blocker", "open_question")
_STATE_KEYS = ("waiting_on", "suspended_by", "reason")


def now() -> datetime:
    return datetime.fromtimestamp(float(os.environ.get("LIBRARIAN_NOW") or time.time()), UTC)


def current_view(
    conn: sqlite3.Connection, workspace: str, record_id: int, cfg: dict[str, Any], at: datetime | None = None
) -> dict[str, Any] | None:
    view = records.get(conn, workspace, record_id)
    if view is None:
        return None
    log = events.for_record(conn, workspace, record_id)
    evidence = [
        (stale.evidence_time(loc, retrieved), role)
        for loc, role, retrieved in conn.execute(
            "SELECT locator, role, retrieved_at FROM evidence WHERE workspace = ? AND record_id = ? ORDER BY id",
            (workspace, record_id),
        )
    ]
    completed_at = max((t for t, role in evidence if role == "completes"), default=None)
    lifecycle = view.get("lifecycle", "open")
    done_at = completed_at
    if lifecycle == "done" and view["kind"] in _EARNED_DONE and completed_at is None:
        lifecycle = "open"
    for entry in log:
        lifecycle, done_at = _apply(conn, view, entry, lifecycle, done_at)
    if lifecycle == "done" and done_at:
        view["done_at"] = done_at.isoformat()
    view["lifecycle"] = lifecycle
    view["history"] = [
        {"event": e["event"], "at": e["at"], **({"change": e["detail"]} if e["detail"] else {})} for e in log
    ]
    last = max((t for t, _ in evidence), default=None)
    if last:
        view["last_evidence"] = last.isoformat()
    view["stale"] = stale.is_stale(view["kind"], lifecycle, last, at or now(), cfg)
    settled = {e["detail"]["with"] for e in log if e["event"] == "resolve_disagreement" and "with" in e["detail"]}
    view["contradictions"] = [c for c in _contradictions(conn, workspace, record_id) if c["id"] not in settled]
    view["links"] = [link for link in view["links"] if link["type"] != "contradicts"]
    if log and not conn.execute(
        "SELECT 1 FROM unit_records WHERE workspace = ? AND record_id = ?", (workspace, record_id)
    ).fetchone():
        view["no_longer_found"] = "no longer found in sources"
    return view


def _apply(
    conn: sqlite3.Connection, view: dict[str, Any], entry: dict[str, Any], lifecycle: str, done_at: datetime | None
) -> tuple[str, datetime | None]:
    detail = entry["detail"]
    if entry["event"] in ("status_change", "owner_change", "project_move", "accept_suggestion", "resolve_disagreement"):
        view["basis"] = "confirmed"
    if "lifecycle" in detail:
        lifecycle = detail["lifecycle"]
        done_at = datetime.fromisoformat(entry["at"]) if lifecycle == "done" else None
        for key in _STATE_KEYS:
            view.pop(key, None)
        view.update({k: detail[k] for k in _STATE_KEYS if k in detail})
    if "person_id" in detail:
        row = conn.execute("SELECT name, is_me FROM persons WHERE id = ?", (detail["person_id"],)).fetchone()
        view["owner"] = row[0]
        view.pop("owner_is_me", None)
        if row[1]:
            view["owner_is_me"] = True
    if "project_id" in detail:
        title = conn.execute("SELECT title FROM records WHERE id = ?", (detail["project_id"],)).fetchone()[0]
        view["projects"] = [{"id": detail["project_id"], "title": title}]
    return lifecycle, done_at


def _contradictions(conn: sqlite3.Connection, workspace: str, record_id: int) -> list[dict[str, Any]]:
    """The Records on the other end of a contradicts Link, whichever side it was stored from, with their Evidence."""
    other_ids = [
        row[0]
        for row in conn.execute(
            "SELECT CASE WHEN from_id = ? THEN to_id ELSE from_id END FROM links"
            " WHERE workspace = ? AND type = 'contradicts' AND from_type = 'record' AND to_type = 'record'"
            " AND ? IN (from_id, to_id) ORDER BY id",
            (record_id, workspace, record_id),
        )
    ]
    out = []
    for other in other_ids:
        got = records.get(conn, workspace, other)
        out.append({k: got[k] for k in ("id", "kind", "title", "evidence")})
    return out
