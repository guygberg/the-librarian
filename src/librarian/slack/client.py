"""Real Slack Web API client behind the SlackSource port. Read-only: only allow-listed methods can be called.

The login is the vendored Slack skill's saved login: a JSON file (path from config
`slack_login_path`) with `token` and, for browser-session tokens, `cookie`. That layout is assumed.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

READ_METHODS = frozenset({"auth.test", "conversations.list", "conversations.history", "conversations.replies", "users.list"})
PAGE_LIMIT = 200
MAX_RETRIES = 5

Http = Callable[[str, dict[str, str], dict[str, str]], tuple[int, dict[str, str], dict[str, Any]]]


def _urllib_http(url: str, params: dict[str, str], headers: dict[str, str]):
    request = urllib.request.Request(url, urllib.parse.urlencode(params).encode(), headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, dict(response.headers), json.load(response)
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers), {}


class SlackClient:
    def __init__(
        self,
        login_path: Path | str | None,
        http: Http = _urllib_http,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._login_path = login_path
        self._http = http
        self._sleep = sleep

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "SlackClient":
        return cls(config.get("slack_login_path"))

    def _headers(self) -> dict[str, str]:
        if not self._login_path:
            raise RuntimeError("no Slack login: set `slack_login_path` in the config to the Slack skill's saved login")
        login = json.loads(Path(self._login_path).read_text())
        headers = {"Authorization": f"Bearer {login['token']}"}
        if login.get("cookie"):
            headers["Cookie"] = login["cookie"]
        return headers

    def _call(self, method: str, **params: Any) -> dict[str, Any]:
        if method not in READ_METHODS:
            raise ValueError(f"Slack method {method!r} is not a read method")
        sent = {k: str(v) for k, v in params.items() if v is not None}
        for attempt in range(MAX_RETRIES + 1):
            status, headers, body = self._http(f"https://slack.com/api/{method}", sent, self._headers())
            if status == 429 and attempt < MAX_RETRIES:
                self._sleep(float(headers.get("Retry-After", 2**attempt)))
                continue
            if status != 200 or not body.get("ok"):
                raise RuntimeError(f"Slack {method} failed: HTTP {status} {body.get('error', '')}".strip())
            return body
        raise AssertionError("unreachable")

    def auth_info(self) -> dict[str, Any]:
        return self._call("auth.test")

    def list_conversations(self) -> list[dict[str, Any]]:
        conversations, cursor = [], None
        while True:
            page = self._call(
                "conversations.list", types="public_channel,private_channel,mpim,im", limit=PAGE_LIMIT, cursor=cursor
            )
            conversations += page["channels"]
            cursor = (page.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                return conversations

    def list_users(self) -> list[dict[str, Any]]:
        users, cursor = [], None
        while True:
            page = self._call("users.list", limit=PAGE_LIMIT, cursor=cursor)
            users += page["members"]
            cursor = (page.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                return users

    def history(self, channel: str, cursor: str | None = None) -> dict[str, Any]:
        return self._call("conversations.history", channel=channel, limit=PAGE_LIMIT, cursor=cursor)

    def replies(self, channel: str, thread_ts: str) -> list[dict[str, Any]]:
        messages, cursor = [], None
        while True:
            page = self._call("conversations.replies", channel=channel, ts=thread_ts, limit=PAGE_LIMIT, cursor=cursor)
            messages += page["messages"]
            cursor = (page.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                return messages
