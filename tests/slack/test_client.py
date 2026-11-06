import json

import pytest

from librarian.slack import permalink
from librarian.slack.client import READ_METHODS, SlackClient


@pytest.fixture
def login(tmp_path):
    path = tmp_path / "login.json"
    path.write_text(json.dumps({"token": "xoxc-1", "cookie": "d=abc"}))
    return path


class Stub:
    """Scripted HTTP layer: pops one (status, headers, body) per request and records the calls."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, params, headers):
        self.calls.append((url, params, headers))
        return self.responses.pop(0)


def ok(**body):
    return 200, {}, {"ok": True, **body}


def test_rate_limit_is_retried_after_the_advertised_wait(login):
    http = Stub((429, {"Retry-After": "7"}, {}), ok(url="https://x.slack.com/"))
    slept = []
    client = SlackClient(login, http, slept.append)
    assert client.auth_info()["url"] == "https://x.slack.com/"
    assert slept == [7.0] and len(http.calls) == 2
    assert http.calls[0][2] == {"Authorization": "Bearer xoxc-1", "Cookie": "d=abc"}


def test_gives_up_after_repeated_rate_limits(login):
    http = Stub(*[(429, {"Retry-After": "1"}, {})] * 10)
    with pytest.raises(RuntimeError, match="429"):
        SlackClient(login, http, lambda s: None).auth_info()


def test_replies_follow_cursors_to_the_end(login):
    http = Stub(
        ok(messages=[{"ts": "1"}], response_metadata={"next_cursor": "c2"}),
        ok(messages=[{"ts": "2"}], response_metadata={"next_cursor": ""}),
    )
    assert SlackClient(login, http).replies("C1", "1") == [{"ts": "1"}, {"ts": "2"}]
    assert http.calls[1][1]["cursor"] == "c2" and "cursor" not in http.calls[0][1]


def test_history_returns_one_page_and_api_errors_raise(login):
    http = Stub(ok(messages=[], response_metadata={"next_cursor": "n"}), (200, {}, {"ok": False, "error": "not_in_channel"}))
    client = SlackClient(login, http)
    assert client.history("C1")["response_metadata"]["next_cursor"] == "n"
    with pytest.raises(RuntimeError, match="not_in_channel"):
        client.history("C1")


def test_client_can_only_read(login):
    public = {n for n in dir(SlackClient) if not n.startswith("_")}
    assert public == {"auth_info", "list_users", "list_conversations", "history", "replies", "from_config"}
    assert all(m.split(".")[1] in {"test", "list", "history", "replies"} for m in READ_METHODS)
    with pytest.raises(ValueError, match="not a read method"):
        SlackClient(login, Stub())._call("chat.postMessage", channel="C1", text="x")


def test_missing_login_is_a_clear_error():
    with pytest.raises(RuntimeError, match="slack_login_path"):
        SlackClient.from_config({}).auth_info()


def test_permalink_shapes():
    assert permalink.build("https://a.slack.com/", "C1", "17.000100") == "https://a.slack.com/archives/C1/p17000100"
    assert permalink.build("https://a.slack.com", "C1", "18.5", "17.1").endswith("p185?thread_ts=17.1&cid=C1")
