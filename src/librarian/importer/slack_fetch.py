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
from librarian.ports import SlackSource
from librarian.slack import permalink, picks

SOURCE = "slack"
WINDOW_SECONDS = 30 * 24 * 3600


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


def stage(workspace: str, slack: SlackSource) -> Stage:
    fetched: dict[str, tuple[dict[str, Any], dict[str, str]]] = {}

    def discover(conn: sqlite3.Connection) -> Iterator[tuple[str, str]]:
        picks.seed_once(conn, workspace, paths.workspace_dir(workspace))
        wanted = picks.picked_ids(conn, workspace)
        if not wanted:
            return
        permalink.save_workspace_url(conn, workspace, slack.auth_info()["url"])
        conversations = {c["id"]: c for c in slack.list_conversations()}
        for channel in sorted(wanted & conversations.keys()):
            origin = {"name": picks.rows([conversations[channel]], wanted)[0]["name"],
                      "kind": picks.kind_of(conversations[channel])}
            cutoff = max(_watermark(conn, workspace, channel), f"{int(_now() - WINDOW_SECONDS)}.000000")
            for message in _history_since(slack, channel, cutoff):
                batch = [message]
                if message.get("thread_ts") == message.get("ts") and message.get("reply_count"):
                    batch += [r for r in slack.replies(channel, message["ts"]) if r.get("ts") != message["ts"]]
                for raw in batch:
                    item = _item_id(channel, raw)
                    fetched[item] = (raw, origin)
                    yield SOURCE, item

    def process(conn: sqlite3.Connection, source: str, item: str) -> None:
        if item not in fetched:
            raise LookupError("message was not fetched in this run; it is retried next Import")
        raw, origin = fetched.pop(item)
        _validate(raw)
        store.upsert(
            conn, workspace, SOURCE, item, json.dumps(raw, ensure_ascii=False, sort_keys=True),
            origin_name=origin["name"], origin_kind=origin["kind"],
        )

    return Stage("fetch", process, discover, "fetched")
