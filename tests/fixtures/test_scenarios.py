import json
import sqlite3

import pytest
from fixtures.scenarios import onboarding_hebrew as hebrew
from fixtures.scenarios import payments_cutover as payments
from fixtures.scenarios import project_slack_only as slack_only
from fixtures.scenarios import slack_prompt_injection as injection
from support.cli import run_librarian
from support.recordings import make_env, run_import, search


@pytest.fixture
def world(tmp_path, home, monkeypatch):
    """`world(scenario, now, config)` builds the scenario, picks C001 and imports once (the env is returned)."""
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))

    def make(scenario, now, config=""):
        env, _ = make_env(tmp_path, home, scenario, config)
        env["LIBRARIAN_NOW"] = str(now)
        (home / "workspaces" / "work").mkdir(parents=True, exist_ok=True)
        (home / "workspaces" / "work" / "channels.json").write_text(json.dumps({"picked": ["C001"]}))
        code, out = run_import(home, env)
        assert code == 0, out
        return env

    return make


def rows(home, sql, *params):
    return sqlite3.connect(next(home.rglob("*.db"))).execute(sql, params).fetchall()


def record_id(home, title):
    [(rid,)] = rows(home, "SELECT id FROM records WHERE title = ?", title)
    return rid


def show(home, env, what):
    out = run_librarian(["show", str(what)], home, env=env)
    assert out.returncode == 0, out.stdout
    return json.loads(out.stdout)


def segment_start(item):
    return json.loads(item["revisions"][-1]["content"])["start"]


def test_payments_cutover_has_both_dates_contradicting_with_evidence_and_rejects_the_uncited(world, home):
    env = world("payments-cutover", payments.NOW)

    nov_18, nov_25 = show(home, env, record_id(home, payments.NOV_18)), show(home, env, record_id(home, payments.NOV_25))
    assert record_id(home, payments.PROJECT) == payments.PROJECT_ID and nov_18["id"] == payments.NOV_18_ID
    assert [c["title"] for c in nov_18["contradictions"]] == [payments.NOV_25]
    assert [c["title"] for c in nov_25["contradictions"]] == [payments.NOV_18]
    assert nov_25["evidence"][0]["quote"] == "Nov 25 to be safe"
    assert nov_25["evidence"][0]["locator"].startswith("drive:") and nov_18["evidence"][0]["locator"].startswith("slack:")
    assert nov_18["evidence"][0]["quote"] == "the cutover is Nov 18"
    assert [rid for (rid,) in rows(home, "SELECT id FROM records WHERE title IN (?, ?)", *payments.UNCITED)] == []
    [blocker] = rows(home, "SELECT id FROM records WHERE kind = 'blocker'")
    assert [(link["type"], link["to"]) for link in show(home, env, blocker[0])["links"]] == [("owner", "Raz Peretz")]

    runs = run_librarian(["runs"], home, env=env).stdout
    assert "rejected 2 (2 no_evidence)" in runs


def test_payments_recording_line_is_at_00_41_10(world, home):
    env = world("payments-cutover", payments.NOW)
    [hit] = search(home, "Nov 25 to be safe")
    assert segment_start(show(home, env, hit["locator"])) == 2470.0


def test_onboarding_hebrew_has_the_item_the_uncertain_word_and_the_stale_ownerless_question(world, home):
    env = world("onboarding-hebrew", hebrew.NOW, hebrew.CONFIG)

    signup = show(home, env, record_id(home, hebrew.SIGNUP))
    assert signup["evidence"][0]["quote"] == hebrew.SIGNUP_LINE and signup["body"] == hebrew.SIGNUP_GLOSS

    [hit] = search(home, "Thursday")
    segment = show(home, env, hit["locator"])
    assert segment_start(segment) == hebrew.UNCERTAIN_START == 9 * 60 + 14
    assert [w["text"] for w in segment["uncertain_words"]] == ["Thursday"]

    legal = show(home, env, record_id(home, hebrew.LEGAL))
    assert legal["stale"] is True and not legal.get("owner")


def test_project_with_no_recording_has_slack_evidence_only(world, home):
    env = world("project_slack_only", slack_only.NOW)
    project = show(home, env, record_id(home, slack_only.PROJECT))
    action = show(home, env, record_id(home, slack_only.ACTION))
    assert [project["title"]] == [slack_only.PROJECT] and action["projects"][0]["title"] == slack_only.PROJECT
    assert rows(home, "SELECT locator FROM evidence WHERE NOT locator LIKE 'slack:%'") == []
    assert rows(home, "SELECT 1 FROM source_items WHERE source = 'drive'") == []


def test_prompt_injection_message_is_plain_text_and_changes_no_record(world, home):
    env = world("slack_prompt_injection", injection.NOW)
    snapshot = lambda: (  # noqa: E731
        rows(home, "SELECT id, kind, title, lifecycle, basis, updated_at FROM records ORDER BY id"),
        rows(home, "SELECT * FROM record_events ORDER BY 1"),
    )
    before = snapshot()
    assert len(before[0]) == 1 and before[1] == []

    code, out = run_import(home, env)

    assert code == 0, out
    assert snapshot() == before
    stored = rows(home, "SELECT r.content FROM source_items i JOIN source_item_revisions r ON r.source_item_id = i.id")
    assert any(json.loads(content)["text"] == injection.INJECTION for (content,) in stored)
    assert show(home, env, record_id(home, injection.TITLE))["lifecycle"] == "open"
