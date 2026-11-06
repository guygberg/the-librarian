import json
import sqlite3

import pytest

from fixtures.build import build
from fixtures.scenarios import onboarding_hebrew as hebrew
from fixtures.scenarios import session_librarian_echo as session
from support.cli import finish_tty, popen_librarian_tty, run_librarian
from support.recordings import make_env, run_import, search
from support.serve import spawn


def show(home, locator):
    out = run_librarian(["show", locator], home)
    return out.returncode, json.loads(out.stdout)


@pytest.fixture
def onboarding(tmp_path, home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    env, _ = make_env(tmp_path, home, "onboarding-hebrew", hebrew.CONFIG)
    env["LIBRARIAN_NOW"] = str(hebrew.NOW)
    (home / "workspaces" / "work").mkdir(parents=True, exist_ok=True)
    (home / "workspaces" / "work" / "channels.json").write_text(json.dumps({"picked": ["C001"]}))
    code, out = run_import(home, env)
    assert code == 0, out
    return home


def marked(items):
    return [i["locator"] for i in items if i["evidence"]]


def test_recording_window_lists_segments_with_timestamps_flags_and_uncertain_spans(onboarding):
    [hit] = search(onboarding, "Thursday")
    code, answer = show(onboarding, hit["locator"])
    assert code == 0
    items = answer["context"]["items"]
    assert marked(items) == [hit["locator"]]
    assert [i["start"] for i in items] == sorted(i["start"] for i in items)
    here = next(i for i in items if i["evidence"])
    assert here["start"] == hebrew.UNCERTAIN_START
    assert (here["title"], here["date"]) == ("Onboarding", "2026-10-20")
    assert items[0]["segment"] == here["segment"] - 1  # the line before is far outside the window
    assert [w["text"] for w in here["uncertain_words"]] == ["Thursday"]
    assert any(i.get("confidence", {}).get("label") == "low confidence" for i in items)
    assert list(answer)[:5] == ["warnings", "resolved", "records", "evidence", "freshness"]


def test_gloss_of_the_evidence_quote_is_labelled_machine_translation(onboarding):
    conn = sqlite3.connect(next(onboarding.rglob("*.db")))
    with conn:
        conn.execute(
            "UPDATE evidence SET gloss = ? WHERE quote = ?",
            (hebrew.SIGNUP_GLOSS, hebrew.SIGNUP_LINE),
        )
    locator = conn.execute(
        "SELECT locator FROM evidence WHERE quote = ?", (hebrew.SIGNUP_LINE,)
    ).fetchone()[0]
    _, answer = show(onboarding, locator)
    [gloss] = answer["context"]["glosses"]
    assert (gloss["quote"], gloss["gloss"], gloss["label"]) == (
        hebrew.SIGNUP_LINE,
        hebrew.SIGNUP_GLOSS,
        "machine translation",
    )


def test_slack_thread_marks_only_the_evidence_message(onboarding):
    locator = f"slack:C001/{hebrew.LEGAL_AT}"
    code, answer = show(onboarding, locator)
    assert code == 0
    assert marked(answer["context"]["items"]) == [locator]
    assert answer["context"]["items"][0]["text"] == hebrew.LEGAL_TEXT


def test_deleted_slack_message_is_flagged_in_the_passage_and_the_record_evidence_and_stays_visible(
    onboarding,
):
    locator = f"slack:C001/{hebrew.LEGAL_AT}"
    conn = sqlite3.connect(next(onboarding.rglob("*.db")))
    with conn:
        conn.execute(
            "UPDATE source_items SET gone = 1 WHERE source = 'slack' AND stable_id = ?",
            (f"C001/{hebrew.LEGAL_AT}",),
        )
    [(record_id,)] = conn.execute(
        "SELECT record_id FROM evidence WHERE locator = ?", (locator,)
    ).fetchall()

    _, answer = show(onboarding, locator)
    [mine] = [i for i in answer["context"]["items"] if i["evidence"]]
    assert mine["gone_from_source"] is True and mine["text"] == hebrew.LEGAL_TEXT

    _, record = show(onboarding, str(record_id))
    [shown] = [e for e in record["evidence"] if e["locator"] == locator]
    assert shown["gone_from_source"] is True and shown["quote"]


def test_session_passage_has_the_copied_lines_and_the_raw_view(tmp_path, home):
    fixtures = tmp_path / "fixtures"
    build(fixtures, "session_librarian_echo")
    home.mkdir()
    (home / "config.toml").write_text(
        'account_type = "team"\nusage_rules_confirmed = true\n'
        f'claude_projects_dir = "{fixtures / "claude" / "projects"}"\n'
    )
    code, out = finish_tty(
        popen_librarian_tty(
            ["import"], home, {"LIBRARIAN_ENGINES": "fake", "LIBRARIAN_FIXTURES": str(fixtures)}
        )
    )
    assert code == 0, out
    locator = f"session:{session.SESSION_ID}/4"
    code, answer = show(home, locator)
    assert code == 0
    items = answer["context"]["items"]
    assert marked(items) == [locator]
    assert [i["line"] for i in items] == [1, 2, 4]
    assert json.loads(items[2]["raw"])["text"] == "the cutover moved to Dec 1"


@pytest.mark.parametrize(
    "locator", ["slack:C001/1.0", "session:nope/3", "drive:zzzz/1", "bogus:a/1"]
)
def test_unknown_locator_is_a_not_found_error(onboarding, locator):
    code, answer = show(onboarding, locator)
    assert code == 1 and answer["error"]["code"] == "not_found"


def test_the_http_route_returns_the_context_and_404s_when_unknown(onboarding):
    locator = f"slack:C001/{hebrew.LEGAL_AT}"
    proc, served = spawn(onboarding, "--port", "0")
    try:
        headers = {"X-Librarian-Token": served.token()}
        resp, data = served.request("GET", f"/api/context?locator={locator}", headers)
        assert resp.status == 200
        assert json.loads(data)["context"] == show(onboarding, locator)[1]["context"]
        assert (
            served.request("GET", "/api/context?locator=slack:C001/1.0", headers)[0].status == 404
        )
        assert served.request("GET", "/api/context", headers)[0].status == 400
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        proc.stdout.close()
