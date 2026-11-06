"""The speaker of a transcript segment, set by hand. First-person lines of a recording stay "unknown speaker" until then.

The setting is a row in `segment_speakers` (kept through re-transcription, matched by time overlap) plus a
`set_speaker` Person event on each Record built from the segment."""

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from librarian import events, locator, store
from librarian.link import review
from librarian.link.review_actions import Invalid, settle


def _segment(conn: sqlite3.Connection, workspace: str, locator_text: str) -> dict[str, Any]:
    try:
        loc = locator.parse(locator_text)
    except ValueError as err:
        raise Invalid(400, str(err)) from err
    content = store.latest_content(conn, workspace, loc.source, loc.stable_id) if loc.source == "drive" else None
    if content is None:
        raise Invalid(404, f"no transcript segment {locator_text!r}")
    return {**json.loads(content), "locator": f"drive:{loc.stable_id}"}


def set_speaker(conn: sqlite3.Connection, workspace: str, locator_text: str, person_id: int) -> list[int]:
    """Returns the Records whose owner this replaced "unknown speaker" for."""
    segment = _segment(conn, workspace, locator_text)
    if not conn.execute("SELECT 1 FROM persons WHERE workspace = ? AND id = ?", (workspace, person_id)).fetchone():
        raise Invalid(404, f"no person {person_id}")
    at = datetime.now(UTC).isoformat()
    conn.execute(
        'INSERT OR REPLACE INTO segment_speakers (workspace, path, start, "end", person_id, at) VALUES (?, ?, ?, ?, ?, ?)',
        (workspace, segment["path"], segment["start"], segment["end"], person_id, at),
    )
    changed = []
    for record_id, entry_id in conn.execute(
        "SELECT DISTINCT e.record_id, r.id FROM evidence e JOIN review_entries r ON r.record_id = e.record_id"
        " WHERE e.workspace = ? AND (e.locator = ? OR e.locator LIKE ?) AND r.kind = ? AND r.link_type = 'owner'"
        " AND r.resolved_at IS NULL",
        (workspace, segment["locator"], segment["locator"] + "#%", review.UNKNOWN_SPEAKER),
    ).fetchall():
        conn.execute("UPDATE records SET owner_person_id = ? WHERE id = ?", (person_id, record_id))
        settle(conn, entry_id, "accepted")
        events.append(conn, workspace, record_id, "set_speaker", {"person_id": person_id, "locator": segment["locator"]})
        changed.append(record_id)
    return changed


def known(conn: sqlite3.Connection, workspace: str, evidence: list[dict[str, Any]]) -> int | None:
    """The Person set as speaker of a segment the Evidence cites, matching the segment's time span by overlap."""
    for ev in evidence:
        loc = locator.parse(ev["locator"])
        content = store.latest_content(conn, workspace, loc.source, loc.stable_id) if loc.source == "drive" else None
        if content is None:
            continue
        seg = json.loads(content)
        row = conn.execute(
            'SELECT person_id FROM segment_speakers WHERE workspace = ? AND path = ? AND start < ? AND "end" > ?'
            ' ORDER BY min("end", ?) - max(start, ?) DESC LIMIT 1',
            (workspace, seg["path"], seg["end"], seg["start"], seg["end"], seg["start"]),
        ).fetchone()
        if row:
            return row[0]
    return None
