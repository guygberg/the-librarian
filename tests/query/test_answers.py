import json
import sqlite3

import pytest

from fixtures.scenarios import payments_cutover as payments
from fixtures.scenarios import project_slack_only as slack_only
from support.cli import run_librarian
from support.recordings import make_env, run_import
from support.serve import spawn

FAR_FUTURE = "4102444800"  # 2100-01-01


@pytest.fixture
def world(tmp_path, home, monkeypatch):
    """`world(scenario, now)` imports the scenario at its own time; the env to ask with is
    returned."""
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))

    def make(scenario="payments-cutover", now=payments.NOW):
        env, _ = make_env(tmp_path, home, scenario)
        env["LIBRARIAN_NOW"] = str(now)
        (home / "workspaces" / "work").mkdir(parents=True, exist_ok=True)
        (home / "workspaces" / "work" / "channels.json").write_text(
            json.dumps({"picked": ["C001"]})
        )
        code, out = run_import(home, env)
        assert code == 0, out
        return env

    return make


def ask(home, env, *args):
    out = run_librarian(list(args), home, env=env)
    assert out.returncode == 0, out.stdout
    return json.loads(out.stdout)


def sql(home, query, *params):
    db = sqlite3.connect(next(home.rglob("*.db")))
    with db:
        return db.execute(query, params).fetchall()


def test_changes_states_the_meeting_and_its_date(world, home):
    answer = ask(home, world(), "changes", "--project", "payments")
    assert answer["resolved"]["project"]["name"] == payments.PROJECT
    assert answer["resolved"]["baseline"] == "since the last meeting, Payments sync, on 2023-11-13"
    assert {r["title"] for r in answer["records"]} >= {payments.PROJECT, payments.NOV_25}
    assert answer["person_events"] == []


def test_changes_with_no_recording_falls_back_to_seven_days_and_says_so(world, home):
    env = world("project-slack-only", slack_only.NOW)
    answer = ask(home, env, "changes", "--project", "helios")
    assert answer["resolved"]["baseline"] == "no meeting found; the last 7 days, since 2023-11-07"
    assert {r["title"] for r in answer["records"]} == {slack_only.PROJECT, slack_only.ACTION}
    later = ask(home, {**env, "LIBRARIAN_NOW": FAR_FUTURE}, "changes", "--project", "helios")
    assert later["records"] == [] and later["resolved"]["baseline"].startswith("no meeting found")


def test_changes_without_a_project_uses_the_latest_recording_overall(world, home):
    answer = ask(home, world(), "changes")
    assert answer["resolved"]["project"] is None and "2023-11-13" in answer["resolved"]["baseline"]


def test_changes_shows_the_persons_own_actions_posted_over_http(world, home):
    env = world()
    proc, served = spawn(home, "--port", "0", env=env)
    try:
        [(blocker,)] = sql(home, "SELECT id FROM records WHERE title = ?", payments.BLOCKER)
        headers = {"Content-Type": "application/json", "X-Librarian-Token": served.token()}
        resp, _ = served.request("POST", f"/api/records/{blocker}/done", headers, "{}")
        assert resp.status == 200
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        proc.stdout.close()
    answer = ask(home, env, "changes", "--project", "payments")
    [event] = answer["person_events"]
    assert (event["record_id"], event["event"], event["change"]) == (
        blocker,
        "status_change",
        {"lifecycle": "done"},
    )


def test_changes_with_an_unclear_project_returns_candidates(world, home):
    answer = ask(home, world(), "changes", "--project", "zzz")
    assert answer["warnings"][0]["code"] == "project_not_found" and answer["records"] == []


def test_waiting_names_who_owns_the_next_step(world, home):
    env = world()
    assert ask(home, env, "waiting")["waiting"] == []
    [(blocker,)] = sql(home, "SELECT id FROM records WHERE title = ?", payments.BLOCKER)
    sql(
        home,
        "INSERT INTO record_events (workspace, record_id, event, detail, at)"
        " VALUES ('work', ?, 'status_change', ?, ?)",
        blocker,
        json.dumps({"lifecycle": "pending", "waiting_on": "Dana Levi"}),
        "2023-11-14T20:00:00+00:00",
    )
    answer = ask(home, env, "waiting")
    assert answer["waiting"] == [
        {"record_id": blocker, "title": payments.BLOCKER, "next_step_owner": "Dana Levi"}
    ]
    assert [r["id"] for r in answer["records"]] == [blocker]


def test_decision_gives_the_reasoning_and_its_evidence(world, home):
    answer = ask(home, world(), "decision", "webhook v1")
    [found] = answer["decisions"]
    assert (found["title"], found["reasoning"]) == (payments.WEBHOOK, "agreed in the thread")
    cited = [e for e in answer["evidence"] if e["record_id"] == found["record_id"]]
    assert (
        cited
        and cited[0]["locator"].startswith("slack:C001/")
        and cited[0]["quote"] == "We keep webhook v1"
    )


def test_decision_with_no_match_says_so(world, home):
    answer = ask(home, world(), "decision", "kubernetes")
    assert answer["decisions"] == [] and answer["warnings"][0]["code"] == "decision_not_found"


def test_blocked_lists_blockers_and_what_they_block(world, home):
    env = world()
    expected = [
        {
            "record_id": 4,
            "title": payments.BLOCKER,
            "owner": "Raz Peretz",
            "blocks": [{"id": payments.PROJECT_ID, "title": payments.PROJECT}],
        }
    ]
    assert ask(home, env, "blocked")["blocked"] == expected
    assert ask(home, env, "blocked", "--project", "payments")["blocked"] == expected
