import json
import sqlite3

import pytest

from fixtures.scenarios import payments_cutover as payments
from librarian.fakes.calllog import CallLog
from support.cli import run_librarian
from support.recordings import make_env, run_import
from support.serve import spawn

JSON = {"Content-Type": "application/json"}
NOW = str(payments.NOW)


class Api:
    def __init__(self, served, home, env):
        self.served, self.home, self.env = served, home, env
        self.headers = {**JSON, "X-Librarian-Token": served.token()}
        [(self.nov_25,)] = self.sql("SELECT id FROM records WHERE title = ?", payments.NOV_25)

    def post(self, record_id, action, body=None, headers=None):
        resp, data = self.served.request(
            "POST",
            f"/api/records/{record_id}/{action}",
            headers or self.headers,
            json.dumps(body or {}),
        )
        return resp.status, json.loads(data)

    def sql(self, query, *params):
        return sqlite3.connect(next(self.home.rglob("*.db"))).execute(query, params).fetchall()

    def show(self, record_id):
        out = run_librarian(["show", str(record_id)], self.home, env=self.env)
        assert out.returncode == 0, out.stdout
        return json.loads(out.stdout)

    def reimport(self):
        code, out = run_import(self.home, self.env)
        assert code == 0, out

    def events(self):
        return self.sql("SELECT record_id, event FROM record_events ORDER BY id")


@pytest.fixture
def api(tmp_path, home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    env, _ = make_env(tmp_path, home, "payments-cutover")
    env["LIBRARIAN_NOW"] = NOW
    (home / "workspaces" / "work").mkdir(parents=True, exist_ok=True)
    (home / "workspaces" / "work" / "channels.json").write_text(json.dumps({"picked": ["C001"]}))
    code, out = run_import(home, env)
    assert code == 0, out
    proc, served = spawn(home, "--port", "0", env=env)
    yield Api(served, home, env)
    proc.terminate()
    proc.wait(timeout=10)
    proc.stdout.close()


def seed(api):
    """A second project, an action item and a person: the payments scenario's own action
    items are all rejected."""
    conn = sqlite3.connect(next(api.home.rglob("*.db")))
    with conn:
        ids = [
            conn.execute(
                "INSERT INTO records (workspace, kind, title, created_at, updated_at)"
                " VALUES ('work', ?, ?, 'x', 'x')",
                (kind, title),
            ).lastrowid
            for kind, title in (("project", "Billing cleanup"), ("action_item", "Call the bank"))
        ]
        person = conn.execute(
            "INSERT INTO persons (workspace, name, created_at) VALUES ('work', 'Dana Cohen', 'x')"
        ).lastrowid
    return *ids, person


def test_done_reopen_and_owner_return_the_history_and_survive_import(api):
    _, task, person = seed(api)

    status, view = api.post(task, "done")
    assert (status, view["lifecycle"]) == (200, "done") and view["history"][0][
        "event"
    ] == "status_change"
    status, view = api.post(task, "owner", {"person_id": person})
    assert (status, view["owner"]) == (200, "Dana Cohen")
    status, view = api.post(task, "reopen")
    assert (status, view["lifecycle"]) == (200, "open")
    assert [h["event"] for h in view["history"]] == [
        "status_change",
        "owner_change",
        "status_change",
    ]

    api.reimport()
    shown = api.show(task)
    assert (shown["lifecycle"], shown["owner"], shown["basis"]) == (
        "open",
        "Dana Cohen",
        "confirmed",
    )
    assert shown["history"] == view["history"]
    assert api.show(payments.NOV_18_ID)["history"] == []


def test_choose_one_supersedes_the_other_and_clears_the_warning(api):
    status, view = api.post(
        payments.NOV_18_ID, "resolve", {"other": api.nov_25, "outcome": "holds"}
    )
    assert (status, view["lifecycle"], view["contradictions"]) == (200, "open", [])

    api.reimport()
    other = api.show(api.nov_25)
    assert (other["lifecycle"], other["contradictions"]) == ("superseded", [])
    assert api.show(payments.NOV_18_ID)["contradictions"] == []


def test_both_wrong_drops_both_with_the_reason(api):
    status, view = api.post(
        payments.NOV_18_ID, "resolve", {"other": api.nov_25, "outcome": "both_wrong"}
    )
    assert (status, view["lifecycle"], view["contradictions"]) == (200, "dropped", [])
    assert view["history"][0]["change"]["reason"] == "marked wrong by me"

    api.reimport()
    for rid in (payments.NOV_18_ID, api.nov_25):
        shown = api.show(rid)
        assert (shown["lifecycle"], shown["contradictions"], shown["reason"]) == (
            "dropped",
            [],
            "marked wrong by me",
        )


def test_project_move_survives_import(api):
    project, _, _ = seed(api)

    status, view = api.post(payments.NOV_18_ID, "project", {"project_id": project})
    assert (status, view["projects"]) == (200, [{"id": project, "title": "Billing cleanup"}])

    api.reimport()
    assert api.show(payments.NOV_18_ID)["projects"] == [{"id": project, "title": "Billing cleanup"}]


def test_guards_refuse_without_token_or_with_foreign_origin_and_write_nothing(api):
    for headers in (JSON, {**api.headers, "Origin": "http://evil.test"}):
        assert api.post(payments.NOV_18_ID, "done", headers=headers)[0] == 403
    assert api.events() == []


@pytest.mark.parametrize(
    ("record", "action", "body", "status"),
    [
        ("project", "done", {}, 409),
        ("decision", "owner", {"person_id": 1}, 409),
        ("decision", "project", {"project_id": 99}, 404),
        ("decision", "resolve", {"other": 1, "outcome": "holds"}, 409),
        ("decision", "resolve", {"other": 2, "outcome": "maybe"}, 400),
        ("missing", "reopen", {}, 404),
    ],
)
def test_invalid_actions_are_refused_and_write_nothing(api, record, action, body, status):
    target = (
        999
        if record == "missing"
        else payments.PROJECT_ID
        if record == "project"
        else payments.NOV_18_ID
    )
    assert api.post(target, action, body)[0] == status
    assert api.events() == []


def test_actions_never_write_to_a_source(api):
    before = CallLog(api.home / "workspaces" / "work").read()
    api.post(payments.NOV_18_ID, "done")
    api.post(payments.NOV_18_ID, "resolve", {"other": api.nov_25, "outcome": "both_wrong"})
    after = CallLog(api.home / "workspaces" / "work").read()
    assert after == before
    assert not [c for c in after if c["method"].startswith(("post", "send", "write", "update"))]
