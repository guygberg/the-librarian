"""The saved list of picked Slack conversations. Nothing is imported unless it is on this list."""

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SEED_FILE = "channels.json"


def kind_of(conversation: dict[str, Any]) -> str:
    if conversation.get("is_im"):
        return "DM"
    if conversation.get("is_mpim"):
        return "group DM"
    if conversation.get("is_private") or conversation.get("is_group"):
        return "private"
    return "public"


def picked_ids(conn: sqlite3.Connection, workspace: str) -> set[str]:
    rows = conn.execute("SELECT conversation_id FROM slack_picks WHERE workspace = ?", (workspace,))
    return {row[0] for row in rows}


def seed_once(conn: sqlite3.Connection, workspace: str, workspace_dir: Path) -> None:
    """Copy ids from `channels.json` (a list, or {"picked": [...]}) the first time only."""
    if conn.execute(
        "SELECT 1 FROM slack_picks_seeded WHERE workspace = ?", (workspace,)
    ).fetchone():
        return
    seed = workspace_dir / SEED_FILE
    ids: list[str] = []
    if seed.exists():
        data = json.loads(seed.read_text())
        ids = data["picked"] if isinstance(data, dict) else data
    with conn:
        conn.execute("INSERT INTO slack_picks_seeded VALUES (?)", (workspace,))
        conn.executemany(
            "INSERT OR IGNORE INTO slack_picks VALUES (?, ?)", [(workspace, i) for i in ids]
        )


def edit_picks(
    conn: sqlite3.Connection, workspace: str, pick: Iterable[str] = (), unpick: Iterable[str] = ()
) -> set[str]:
    """The one writer of the list; the terminal command and the HTTP API both call it."""
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO slack_picks VALUES (?, ?)", [(workspace, i) for i in pick]
        )
        conn.executemany(
            "DELETE FROM slack_picks WHERE workspace = ? AND conversation_id = ?",
            [(workspace, i) for i in unpick],
        )
    return picked_ids(conn, workspace)


def rows(conversations: list[dict[str, Any]], picked: set[str]) -> list[dict[str, Any]]:
    """Display rows for every conversation the login can see, newest API order kept."""
    return [
        {
            "id": c["id"],
            "name": c.get("name") or c.get("user") or c["id"],
            "kind": kind_of(c),
            "members": c.get("num_members"),
            "picked": c["id"] in picked,
        }
        for c in conversations
    ]
