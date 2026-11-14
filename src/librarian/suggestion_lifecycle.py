"""Retiring Suggestions. History is never edited or deleted: a retired Suggestion becomes
`superseded` with an event saying why, and gives up its dedupe key so the same proposal can be
made again.
"""

import json
import sqlite3
from collections.abc import Iterable

from librarian.clock import utc_now_iso


def supersede(conn: sqlite3.Connection, workspace: str, ids: Iterable[int], reason: str) -> int:
    """Supersede each Suggestion that is not already superseded; return how many were."""
    now = utc_now_iso()
    changed = 0
    for suggestion_id in sorted(set(ids)):
        cur = conn.execute(
            "UPDATE suggestions SET status = 'superseded', resolved_at = ?,"
            " dedupe_key = dedupe_key || '#superseded:' || id"
            " WHERE id = ? AND workspace = ? AND status != 'superseded'",
            (now, suggestion_id, workspace),
        )
        if cur.rowcount:
            changed += 1
            conn.execute(
                "INSERT INTO suggestion_events (workspace, suggestion_id, event, detail, at)"
                " VALUES (?, ?, 'superseded', ?, ?)",
                (workspace, suggestion_id, json.dumps({"reason": reason}), now),
            )
    return changed


def marks(ids: list[int]) -> str:
    return ", ".join("?" * len(ids))


def forget_sources(
    conn: sqlite3.Connection,
    workspace: str,
    revisions: list[int],
    item_ids: list[int],
    record_ids: list[int],
) -> None:
    """Called inside forget's transaction, before the revisions and Records are deleted: drop the
    Evidence on them, and supersede every Suggestion left with no Evidence or pointing at a
    deleted Source item or Record."""
    if not (revisions or item_ids or record_ids):
        return
    hit: set[int] = set()
    if revisions:
        hit |= {
            s
            for (s,) in conn.execute(
                "SELECT DISTINCT suggestion_id FROM suggestion_evidence"
                f" WHERE revision_id IN ({marks(revisions)})",
                revisions,
            )
        }
        conn.execute(
            f"DELETE FROM suggestion_evidence WHERE revision_id IN ({marks(revisions)})", revisions
        )
    for end_type, ids in (("source_item", item_ids), ("record", record_ids)):
        if ids:
            for side in ("from", "to"):
                hit |= {
                    s
                    for (s,) in conn.execute(
                        f"SELECT id FROM suggestions WHERE {side}_type = ? AND {side}_id"
                        f" IN ({marks(ids)})",
                        [end_type, *ids],
                    )
                }
    bare = [
        s
        for s in hit
        if not conn.execute(
            "SELECT 1 FROM suggestion_evidence WHERE suggestion_id = ?", (s,)
        ).fetchone()
    ]
    pointing = hit - set(bare)
    supersede(conn, workspace, bare, "source forgotten")
    # Only an end that is gone matters; one whose Evidence merely shrank stays as it is.
    supersede(
        conn,
        workspace,
        [s for s in pointing if _end_gone(conn, s, item_ids, record_ids)],
        "target forgotten",
    )


def _end_gone(conn, suggestion_id: int, item_ids: list[int], record_ids: list[int]) -> bool:
    gone = {"source_item": set(item_ids), "record": set(record_ids)}
    row = conn.execute(
        "SELECT from_type, from_id, to_type, to_id FROM suggestions WHERE id = ?", (suggestion_id,)
    ).fetchone()
    return any(row[i + 1] in gone.get(row[i], ()) for i in (0, 2))
