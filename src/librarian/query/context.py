"""The passage around one Evidence locator, with the Evidence item marked. Read-only: takes a `db.connect_ro` connection.

Slack: the thread. Session: the copied lines around the evidence line. Recording (`drive`): the transcript segments
within a window around the evidence segment, with low-confidence flags and uncertain word spans.
"""

import json
import sqlite3
from typing import Any

from librarian import config, locator
from librarian.query import envelope
from librarian.transcribe import confidence

SESSION_LINES = 5  # each side of the evidence line
RECORDING_SECONDS = 150  # each side of the evidence segment: about 5 minutes in all
GLOSS_LABEL = "machine translation"


def _number(stable_id: str) -> tuple[str, int] | None:
    prefix, _, tail = stable_id.rpartition("/")
    return (prefix, int(tail)) if prefix and tail.isdigit() else None


def _latest(conn: sqlite3.Connection, workspace: str, source: str, like: str) -> list[tuple[str, dict[str, Any], str]]:
    """(stable_id, parsed content, raw content) of the latest revision of every item whose id matches `like`."""
    rows = conn.execute(
        "SELECT i.stable_id, r.content FROM source_items i JOIN source_item_revisions r ON r.source_item_id = i.id"
        " WHERE i.workspace = ? AND i.source = ? AND i.stable_id LIKE ? ESCAPE '\\'"
        " AND r.revision = (SELECT MAX(revision) FROM source_item_revisions WHERE source_item_id = i.id)",
        (workspace, source, like),
    )
    return [(stable_id, parse_content(raw), raw) for stable_id, raw in rows]


def parse_content(raw: str) -> dict[str, Any]:
    """Content that is not a JSON object (a hand-stored item) has no fields to show; it must not break `show`."""
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _like_prefix(prefix: str) -> str:
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"


def _numbered(conn, workspace, source, prefix) -> dict[int, tuple[str, dict[str, Any], str]]:
    """Items `<prefix>/<n>` by n."""
    found = {}
    for sid, content, raw in _latest(conn, workspace, source, _like_prefix(prefix)):
        parsed = _number(sid)
        if parsed and parsed[0] == prefix:
            found[parsed[1]] = (sid, content, raw)
    return found


def _slack(conn, workspace, loc, cfg):
    channel = loc.stable_id.partition("/")[0]
    items = _latest(conn, workspace, "slack", _like_prefix(channel))
    mine = next((m for sid, m, _ in items if sid == loc.stable_id), None)
    if mine is None:
        return None
    root = mine.get("thread_ts") or mine.get("ts")
    thread = sorted(
        ((sid, m) for sid, m, _ in items if m.get("ts") == root or m.get("thread_ts") == root),
        key=lambda pair: pair[1].get("ts", ""),
    )
    return [
        {"locator": str(locator.Locator("slack", sid)), "user": m.get("user"), "ts": m.get("ts"), "text": m.get("text", "")}
        | {"evidence": sid == loc.stable_id}
        for sid, m in thread
    ]


def _session(conn, workspace, loc, cfg):
    parsed = _number(loc.stable_id)
    if parsed is None:
        return None
    session, line = parsed
    items = _numbered(conn, workspace, "session", session)
    if line not in items:
        return None
    return [
        {
            "locator": str(locator.Locator("session", sid)),
            "line": n,
            "role": m.get("role"),
            "timestamp": m.get("timestamp"),
            "text": m.get("text", ""),
            "raw": raw,
            "evidence": n == line,
        }
        for n, (sid, m, raw) in sorted(items.items())
        if abs(n - line) <= SESSION_LINES
    ]


def _recording(conn, workspace, loc, cfg):
    parsed = _number(loc.stable_id)
    if parsed is None:
        return None
    file_id, number = parsed
    segments = _numbered(conn, workspace, "drive", file_id)
    if number not in segments:
        return None
    at = segments[number][1]["start"]
    return [
        {
            "locator": str(locator.Locator("drive", sid)),
            "segment": n,
            "start": m["start"],
            "end": m["end"],
            "text": m["text"],
            "evidence": n == number,
            **confidence.describe(m, cfg),
        }
        for n, (sid, m, _) in sorted(segments.items())
        if abs(m["start"] - at) <= RECORDING_SECONDS
    ]


_PASSAGES = {"slack": _slack, "session": _session, "drive": _recording}


def _glosses(conn: sqlite3.Connection, workspace: str, loc: locator.Locator) -> list[dict[str, Any]]:
    """Evidence quotes of this item that carry a gloss. The gloss is machine translation, never the source's words."""
    rows = conn.execute(
        "SELECT record_id, locator, quote, gloss FROM evidence WHERE workspace = ? AND gloss IS NOT NULL ORDER BY id",
        (workspace,),
    )
    return [
        {"record_id": record_id, "quote": quote, "gloss": gloss, "label": GLOSS_LABEL}
        for record_id, text, quote, gloss in rows
        if _same_item(text, loc)
    ]


def _same_item(text: str, loc: locator.Locator) -> bool:
    try:
        other = locator.parse(text)
    except ValueError:
        return False
    return (other.source, other.stable_id) == (loc.source, loc.stable_id)


def context(conn: sqlite3.Connection, workspace: str, loc: locator.Locator, cfg: dict[str, Any]) -> dict[str, Any] | None:
    """None when the locator names no stored Source item of a known source."""
    passage = _PASSAGES.get(loc.source)
    items = passage(conn, workspace, loc, cfg) if passage else None
    if items is None:
        return None
    return {"locator": str(loc), "source": loc.source, "items": items, "glosses": _glosses(conn, workspace, loc)}


def answer(conn: sqlite3.Connection, workspace: str, text: str) -> tuple[int, dict[str, Any]]:
    """The envelope with a `context` key, or an `error` body, with the HTTP status that goes with it."""
    try:
        loc = locator.parse(text)
    except ValueError as err:
        return 400, {"error": {"code": "bad_locator", "message": str(err)}}
    cfg = config.load()
    found = context(conn, workspace, loc, cfg)
    if found is None:
        return 404, {"error": {"code": "not_found", "message": f"no Source item {loc.source}:{loc.stable_id}"}}
    return 200, envelope.build(conn, workspace, cfg, [], context=found)
