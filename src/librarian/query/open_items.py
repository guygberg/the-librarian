"""The one open-items query.

`librarian open-items` and `GET /api/open-items` both call `open_items`.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from librarian import config, locator
from librarian.link import review
from librarian.query import context, core, envelope, stale
from librarian.transcribe import confidence

KINDS = ("action_item", "blocker", "open_question")
NEEDS, WAITING, OTHER = "needs_attention", "waiting_on_others", "other_open"
GROUPS = (NEEDS, WAITING, OTHER)


def week_start(at: datetime) -> datetime:
    """Sunday 00:00 in `at`'s own zone."""
    midnight = at.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=(midnight.weekday() + 1) % 7)


def group_of(view: dict[str, Any]) -> str | None:
    """None for a Record that is not open.

    Suggested owners never count: only a confirmed or stated owner is an owner.
    """
    if view["lifecycle"] not in stale.UNFINISHED:
        return None
    owner = view.get("owner")
    unknown = owner == review.MARKS[review.UNKNOWN_SPEAKER]
    if not (view.get("owner_is_me") or owner is None or unknown):
        return OTHER
    if view["lifecycle"] == "pending":
        return WAITING
    if view["lifecycle"] == "open" and not any(
        s["link"] == "owner" and s["kind"] == review.UNCONFIRMED_PERSON
        for s in view.get("suggested", [])
    ):
        return NEEDS
    return OTHER


def _mark(view: dict[str, Any]) -> str | None:
    return next((s["mark"] for s in view.get("suggested", []) if s["link"] == "owner"), None)


def _transcription_uncertain(
    conn: sqlite3.Connection, workspace: str, record_id: int, cfg: dict[str, Any]
) -> bool:
    """True when the Record cites a recording segment that is low confidence.

    Also true when the segment holds an uncertain word.
    """
    for (loc,) in conn.execute(
        "SELECT locator FROM evidence WHERE workspace = ? AND record_id = ?", (workspace, record_id)
    ).fetchall():
        parsed = locator.parse(loc)
        if parsed.source != "drive":
            continue
        row = conn.execute(
            "SELECT r.content FROM source_items i"
            " JOIN source_item_revisions r ON r.source_item_id = i.id"
            " WHERE i.workspace = ? AND i.source = 'drive' AND i.stable_id = ?"
            " ORDER BY r.revision DESC LIMIT 1",
            (workspace, parsed.stable_id),
        ).fetchone()
        segment = context.parse_content(row[0]) if row else {}
        if segment and confidence.describe(segment, cfg):
            return True
    return False


def open_items(
    conn: sqlite3.Connection, workspace: str, at: datetime | None = None, everything: bool = False
) -> dict[str, Any]:
    """`everything` (the UI's filters) also lists Records that are not open or not work items.

    Those carry `group` None. It also names every project; headline and progress still
    count only the open work items.
    """
    at = at or core.now()
    cfg = config.load()
    kinds = (*KINDS, "decision") if everything else KINDS
    ids = [
        row[0]
        for row in conn.execute(
            "SELECT id FROM records WHERE workspace = ?"
            f" AND kind IN ({', '.join('?' * len(kinds))}) ORDER BY id",
            (workspace, *kinds),
        )
    ]
    since = week_start(at.astimezone())
    items: list[dict[str, Any]] = []
    done_this_week = still_open = 0
    for record_id in ids:
        view = core.current_view(conn, workspace, record_id, cfg, at)
        group = group_of(view) if view["kind"] in KINDS else None
        owner = view.get("owner")
        own_or_ownerless = (
            view.get("owner_is_me")
            or owner is None
            or owner == review.MARKS[review.UNKNOWN_SPEAKER]
        )
        if view["kind"] == "action_item" and own_or_ownerless:
            if group:
                still_open += 1
            elif view["lifecycle"] == "done" and datetime.fromisoformat(view["done_at"]) >= since:
                done_this_week += 1
        if group or everything:
            if mark := _mark(view):
                view["mark"] = mark
            items.append(
                {
                    **view,
                    "group": group,
                    "transcription_uncertain": _transcription_uncertain(
                        conn, workspace, record_id, cfg
                    ),
                }
            )
    # Flags raise an item within its group; they never add one.
    items.sort(
        key=lambda v: (
            GROUPS.index(v["group"]) if v["group"] else len(GROUPS),
            not (v["stale"] or v["contradictions"]),
        )
    )
    needs = sum(v["group"] == NEEDS for v in items)
    waiting = sum(v["group"] == WAITING for v in items)
    return envelope.build(
        conn,
        workspace,
        cfg,
        items,
        at=at,
        headline={
            "needs_you": needs,
            "waiting": waiting,
            "text": f"{needs} {'thing needs' if needs == 1 else 'things need'} you,"
            f" {waiting} waiting on someone else",
        },
        progress={
            "done_this_week": done_this_week,
            "total": done_this_week + still_open,
            "week_start": since.isoformat(),
        },
        **(
            {"projects": _projects(conn, workspace), "people": _people(conn, workspace)}
            if everything
            else {}
        ),
    )


def _people(conn: sqlite3.Connection, workspace: str) -> list[dict[str, Any]]:
    """Every Person, for choosing an owner."""
    return [
        {"id": row[0], "name": row[1]}
        for row in conn.execute(
            "SELECT id, name FROM persons WHERE workspace = ? ORDER BY id", (workspace,)
        )
    ]


def _projects(conn: sqlite3.Connection, workspace: str) -> list[dict[str, Any]]:
    return [
        {"id": row[0], "title": row[1]}
        for row in conn.execute(
            "SELECT id, title FROM records WHERE workspace = ? AND kind = 'project' ORDER BY id",
            (workspace,),
        )
    ]
