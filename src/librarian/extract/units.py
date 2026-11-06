"""Extraction units: the groups of Source items that go to the extractor in one call.

- Slack: one thread (root and replies), or the loose messages of one channel-day.
- Claude session: SESSION_WINDOW evidence lines at a time.
- Recording: WINDOW_SECONDS of transcript at a time.

A unit's text has one `[locator] speaker: text` line per Source item, so Evidence can point at an item.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

WINDOW_SECONDS = 15 * 60
SESSION_WINDOW = 100
RECORDING_SOURCE = "recording"  # import items are the recording files; their transcript segments are `drive` items


@dataclass
class Unit:
    key: str
    lines: list[str] = field(default_factory=list)
    locators: set[str] = field(default_factory=set)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def add(self, source: str, stable_id: str, speaker: str, text: str) -> None:
        locator = f"{source}:{stable_id}"
        self.lines.append(f"[{locator}] {speaker}: {text}")
        self.locators.add(locator)


def build(conn: sqlite3.Connection, workspace: str) -> dict[tuple[str, str], list[Unit]]:
    """The units of everything stored, by the import item (source, item) that each belongs to."""
    rows = conn.execute(
        "SELECT i.source, i.stable_id, i.origin_name, r.content FROM source_items i"
        " JOIN source_item_revisions r ON r.source_item_id = i.id"
        " WHERE i.workspace = ? AND i.gone = 0"
        " AND r.revision = (SELECT MAX(revision) FROM source_item_revisions WHERE source_item_id = i.id)",
        (workspace,),
    )
    units: dict[str, Unit] = {}
    members: dict[tuple[str, str], dict[str, Unit]] = {}

    def put(key: str, member: tuple[str, str]) -> Unit:
        unit = units.setdefault(key, Unit(key))
        members.setdefault(member, {})[key] = unit
        return unit

    parsed = [(source, stable_id, origin, json.loads(content)) for source, stable_id, origin, content in rows]
    sessions: dict[str, list[tuple[str, dict]]] = {}
    for source, stable_id, origin, content in sorted(parsed, key=_order):
        if source == "slack":
            channel = stable_id.split("/")[0]
            root = content.get("thread_ts")
            key = f"slack-thread-{channel}-{root}" if root else f"slack-day-{channel}-{_day(content.get('ts'))}"
            put(key, ("slack", stable_id)).add(source, stable_id, content.get("user", "?"), content.get("text", ""))
        elif source == "session":
            sessions.setdefault(content["session_id"], []).append((stable_id, content))
        elif source == "drive":
            file_hash = stable_id.split("/")[0]
            key = f"drive-{file_hash}-{int(content['start'] // WINDOW_SECONDS) + 1}"
            put(key, (RECORDING_SOURCE, origin)).add(source, stable_id, "", content["text"])
    for session_id, lines in sessions.items():
        for number, (stable_id, content) in enumerate(lines):
            key = f"session-{session_id}-{number // SESSION_WINDOW + 1}"
            put(key, ("session", stable_id)).add("session", stable_id, content["role"], content["text"])
    return {member: sorted(by_key.values(), key=lambda u: u.key) for member, by_key in members.items()}


def _order(row: tuple[str, str, str, dict]) -> tuple:
    """Chronological inside each source; items of different units may interleave, which is harmless."""
    source, _, _, content = row
    return source, float(content.get("ts") or 0), content.get("line", 0), content.get("segment", 0)


def _day(ts: str | None) -> str:
    return datetime.fromtimestamp(float(ts), UTC).date().isoformat() if ts else "unknown"
