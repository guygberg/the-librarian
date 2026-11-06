"""Slack fetch stage: picked conversations only, last 30 days on first run, newer items afterwards.

Uses the Slack port's read methods only. Discovery pages the history and replies; `process` then
stores each raw message as its own Source item, so one malformed message fails alone.
"""

import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Iterator
from typing import Any

from librarian import paths, store
from librarian.importer.stages import Stage
from librarian.link import people
from librarian.ports import SlackSource
from librarian.slack import permalink, picks

SOURCE = "slack"
WINDOW_SECONDS = 30 * 24 * 3600
# Items newer than this are read again each Import to catch edits and deletions; older ones are not re-checked.
RECHECK_SECONDS = 7 * 24 * 3600


def _now() -> float:
    return float(os.environ.get("LIBRARIAN_NOW") or time.time())


def _watermark(conn: sqlite3.Connection, workspace: str, channel: str) -> str:
    """Newest stored ts of the conversation ('' when nothing is stored yet)."""
    row = conn.execute(
        "SELECT MAX(stable_id) FROM source_items WHERE workspace = ? AND source = ? AND stable_id LIKE ?",
        (workspace, SOURCE, f"{channel}/%"),
    ).fetchone()
    return row[0].split("/", 1)[1] if row[0] else ""


def _history_since(slack: SlackSource, channel: str, cutoff: str) -> Iterator[dict[str, Any]]:
    cursor = None
    while True:
        page = slack.history(channel, cursor)
        messages = page.get("messages", [])
        # A message without a usable ts is kept so that it fails visibly in `process`.
        is_old = [isinstance(m.get("ts"), str) and m["ts"] <= cutoff for m in messages]
        yield from (m for m, old in zip(messages, is_old, strict=True) if not old)
        reached_old = any(is_old)
        cursor = (page.get("response_metadata") or {}).get("next_cursor")
        if not cursor or reached_old:
            return


def _history_before(slack: SlackSource, channel: str, bound: str) -> Iterator[dict[str, Any]]:
    """Every message at or older than `bound`, paging through the newer ones first."""
    cursor = None
    while True:
        page = slack.history(channel, cursor)
        yield from (m for m in page.get("messages", []) if isinstance(m.get("ts"), str) and m["ts"] <= bound)
        cursor = (page.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            return


def _with_replies(
    slack: SlackSource, channel: str, messages: Iterator[dict[str, Any]], threads: set[str]
) -> Iterator[dict[str, Any]]:
    """Each message followed by its thread replies; `threads` collects the parents whose replies were read."""
    for message in messages:
        yield message
        if message.get("thread_ts") == message.get("ts") and message.get("reply_count"):
            threads.add(message["ts"])
            yield from (r for r in slack.replies(channel, message["ts"]) if r.get("ts") != message["ts"])


def count_older(slack: SlackSource, channel: str) -> int:
    """Dry run for `import-older`: how many messages lie beyond the 30-day window."""
    older = _history_before(slack, channel, _window_start())
    return sum(1 for _ in _with_replies(slack, channel, older, set()))


def _window_start() -> str:
    return f"{int(_now() - WINDOW_SECONDS)}.000000"


def _content(raw: dict[str, Any]) -> str:
    return json.dumps(raw, ensure_ascii=False, sort_keys=True)


def _stored_since(conn: sqlite3.Connection, workspace: str, channel: str, cutoff: str) -> dict[str, dict[str, Any]]:
    """Latest stored content of the conversation's items newer than `cutoff`, by item id."""
    rows = conn.execute(
        "SELECT i.stable_id, r.content FROM source_items i JOIN source_item_revisions r ON r.source_item_id = i.id"
        " WHERE i.workspace = ? AND i.source = ? AND i.stable_id > ? AND i.stable_id LIKE ?"
        " AND r.revision = (SELECT MAX(revision) FROM source_item_revisions WHERE source_item_id = i.id)",
        (workspace, SOURCE, f"{channel}/{cutoff}", f"{channel}/%"),
    )
    return {item: json.loads(content) for item, content in rows}


def _mark_missing_gone(
    conn: sqlite3.Connection, workspace: str, channel: str, cutoff: str, seen: set[str], threads: set[str]
) -> None:
    """Items inside the re-check window that Slack no longer returns. Replies count only when their thread was read."""
    for item, message in _stored_since(conn, workspace, channel, cutoff).items():
        parent = message.get("thread_ts")
        if item not in seen and parent in (None, message.get("ts"), *threads):
            store.mark_gone(conn, workspace, SOURCE, item)


def _item_id(channel: str, message: dict[str, Any]) -> str:
    if isinstance(message.get("ts"), str):
        return f"{channel}/{message['ts']}"
    digest = hashlib.sha256(json.dumps(message, sort_keys=True).encode()).hexdigest()[:8]
    return f"{channel}/no-ts-{digest}"


def _validate(message: dict[str, Any]) -> None:
    if not isinstance(message.get("ts"), str):
        raise ValueError("slack message has no 'ts'")
    for field in ("text", "thread_ts", "user"):
        if field in message and not isinstance(message[field], str):
            raise ValueError(f"slack message field {field!r} is not text")


def _cutoff(conn: sqlite3.Connection, workspace: str, channel: str) -> str:
    """Where a normal Import starts reading: the last RECHECK_SECONDS of stored items are read again."""
    window = _window_start()
    watermark = _watermark(conn, workspace, channel)
    if not watermark:
        return window
    return max(window, min(watermark, f"{int(_now() - RECHECK_SECONDS)}.000000"))


def stage(workspace: str, slack: SlackSource, older: str | None = None) -> Stage:
    """The normal fetch stage, or with `older` set only that conversation's history beyond the 30-day window."""
    fetched: dict[str, tuple[dict[str, Any], dict[str, str]]] = {}

    def discover(conn: sqlite3.Connection) -> Iterator[tuple[str, str]]:
        picks.seed_once(conn, workspace, paths.workspace_dir(workspace))
        wanted = picks.picked_ids(conn, workspace)
        if not wanted:
            return
        auth = slack.auth_info()
        permalink.save_workspace_url(conn, workspace, auth["url"])
        people.save_slack_users(conn, workspace, slack.list_users(), auth.get("user_id"))
        conversations = {c["id"]: c for c in slack.list_conversations()}
        for channel in sorted((wanted & conversations.keys()) if older is None else {older} & wanted):
            origin = {"name": picks.rows([conversations[channel]], wanted)[0]["name"],
                      "kind": picks.kind_of(conversations[channel])}
            cutoff = _cutoff(conn, workspace, channel)
            history = (
                _history_since(slack, channel, cutoff) if older is None
                else _history_before(slack, channel, _window_start())
            )
            seen: set[str] = set()
            threads: set[str] = set()
            for raw in _with_replies(slack, channel, history, threads):
                item = _item_id(channel, raw)
                seen.add(item)
                stored = store.latest_content(conn, workspace, SOURCE, item)
                if stored == _content(raw):
                    continue
                if stored is not None:
                    # Edited: earlier stages already finished this item, so make them run again.
                    conn.execute(
                        "DELETE FROM import_item_stages WHERE workspace = ? AND source = ? AND item = ?",
                        (workspace, SOURCE, item),
                    )
                fetched[item] = (raw, origin)
                yield SOURCE, item
            if older is None:
                _mark_missing_gone(conn, workspace, channel, cutoff, seen, threads)

    def process(conn: sqlite3.Connection, source: str, item: str) -> None:
        if item not in fetched:
            raise LookupError("message was not fetched in this run; it is retried next Import")
        raw, origin = fetched.pop(item)
        _validate(raw)
        store.upsert(
            conn, workspace, SOURCE, item, _content(raw),
            origin_name=origin["name"], origin_kind=origin["kind"],
        )

    return Stage("fetch", process, discover, "fetched")
