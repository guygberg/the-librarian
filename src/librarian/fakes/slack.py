"""Fake Slack: replays the fixture pages. Any method beyond the port is write-shaped and fails."""

import json
from pathlib import Path

from librarian.fakes.calllog import CallLog


class FakeSlack:
    def __init__(self, fixtures: Path, log: CallLog):
        self._root = fixtures / "slack"
        self._log = log

    def _generation(self) -> int:
        """Runs started so far, counted by `auth_info` calls (one per Import): 0 on the first."""
        return max(0, sum(c["method"] == "auth_info" for c in self._log.read()) - 1)

    def _load(self, *parts: str):
        """Newest `gen-<n>/` copy of the file at or below the current generation.

        Falls back to the base copy.
        """
        for gen in range(self._generation(), 0, -1):
            path = self._root.joinpath(f"gen-{gen}", *parts)
            if path.exists():
                return json.loads(path.read_text())
        return json.loads(self._root.joinpath(*parts).read_text())

    def auth_info(self) -> dict:
        self._log.record("slack", "auth_info")
        return self._load("auth.test.json")

    def list_conversations(self) -> list[dict]:
        self._log.record("slack", "list_conversations")
        return self._load("conversations.list.json")["channels"]

    def list_users(self) -> list[dict]:
        self._log.record("slack", "list_users")
        return self._load("users.list.json")["members"]

    def history(self, channel: str, cursor: str | None = None) -> dict:
        self._log.record("slack", "history", channel=channel, cursor=cursor)
        page = 0 if not cursor else int(cursor.rsplit("-", 1)[1])
        return self._load("history", channel, f"page-{page}.json")

    def replies(self, channel: str, thread_ts: str) -> list[dict]:
        self._log.record("slack", "replies", channel=channel, thread_ts=thread_ts)
        return self._load("replies", channel, f"{thread_ts}.json")["messages"]

    def __getattr__(self, name: str):
        raise AssertionError(f"write-shaped Slack call attempted: {name}")
