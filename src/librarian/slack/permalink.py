"""Slack permalinks are not in the raw message; they are built from the saved workspace URL."""

import json
import sqlite3

from librarian import store


def build(workspace_url: str, channel: str, ts: str, thread_ts: str | None = None) -> str:
    link = f"{workspace_url.rstrip('/')}/archives/{channel}/p{ts.replace('.', '')}"
    if thread_ts and thread_ts != ts:
        link += f"?thread_ts={thread_ts}&cid={channel}"
    return link


def save_workspace_url(conn: sqlite3.Connection, workspace: str, url: str) -> None:
    with conn:
        conn.execute("INSERT OR REPLACE INTO slack_workspace VALUES (?, ?)", (workspace, url))


def for_item(conn: sqlite3.Connection, workspace: str, stable_id: str) -> str | None:
    """Permalink of a stored `<channel>/<ts>` item, or None when the URL or message is unavailable."""
    row = conn.execute("SELECT url FROM slack_workspace WHERE workspace = ?", (workspace,)).fetchone()
    item = store.get_item(conn, workspace, "slack", stable_id)
    if row is None or item is None:
        return None
    try:
        message = json.loads(item["revisions"][-1]["content"])
        channel, ts = stable_id.split("/", 1)
        return build(row[0], channel, ts, message.get("thread_ts"))
    except (ValueError, AttributeError):
        return None
