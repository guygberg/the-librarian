import json
import os

import pytest

from fixtures import formats as f
from fixtures.build import build
from librarian import db
from librarian.fakes.calllog import CallLog
from support.cli import finish_tty, popen_librarian_tty, run_librarian

NOW = 1_700_000_000
DAY = 86_400
READ_CALLS = {"auth_info", "list_users", "list_conversations", "history", "replies"}


def make_env(tmp_path, home, scenario):
    fixtures = tmp_path / "fixtures"
    build(fixtures, scenario)
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text('account_type = "team"\nusage_rules_confirmed = true\n')
    ws = home / "workspaces" / "work"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "channels.json").write_text(json.dumps({"picked": ["C001"]}))
    return {
        "LIBRARIAN_ENGINES": "fake",
        "LIBRARIAN_FIXTURES": str(fixtures),
        "LIBRARIAN_NOW": str(NOW),
    }


def run_import(home, env):
    code, out = finish_tty(popen_librarian_tty(["import"], home, env))
    return code, out.replace("\r", "")


def query(home, monkeypatch, sql):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    conn = db.connect_ro("work")
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def show(home, locator):
    result = run_librarian(["show", locator], home)
    return json.loads(result.stdout)


@pytest.fixture
def older(tmp_path, home):
    return make_env(tmp_path, home, "slack_history_older")


def test_first_import_covers_last_30_days_of_picked_only(home, older, monkeypatch):
    code, out = run_import(home, older)
    assert code == 0
    assert "slack: fetched 6" in out
    ids = [
        r[0]
        for r in query(home, monkeypatch, "SELECT stable_id FROM source_items ORDER BY stable_id")
    ]
    assert len(ids) == 6 and all(i.startswith("C001/") for i in ids)
    assert all(float(i.split("/")[1]) > NOW - 30 * DAY for i in ids)


def test_item_carries_conversation_name_kind_and_permalinks(home, older):
    run_import(home, older)
    top = show(home, f"slack:C001/{f.ts(NOW - 10 * DAY)}")
    assert top["origin_name"] == "atlas-dev" and top["origin_kind"] == "public"
    assert json.loads(top["revisions"][0]["content"])["text"] == "recent 0"
    assert "permalink" not in json.loads(top["revisions"][0]["content"])
    assert top["permalink"] == f"https://acme-test.slack.com/archives/C001/p{NOW - 10 * DAY}000000"
    parent_ts = f.ts(NOW - 5 * DAY)
    reply = show(home, f"slack:C001/{f.ts(NOW - 5 * DAY + 1)}")
    assert reply["permalink"].endswith(
        f"/archives/C001/p{NOW - 5 * DAY + 1}000000?thread_ts={parent_ts}&cid=C001"
    )


def test_second_import_adds_no_duplicates_and_fetches_only_newer(home, older, monkeypatch):
    run_import(home, older)
    fixtures = older["LIBRARIAN_FIXTURES"]
    from pathlib import Path

    from fixtures.scenarios.slack_history_older import messages  # noqa: PLC0415

    history, _ = messages()
    f.write_slack_history(
        Path(fixtures), "C001", [*history, f.slack_message("U001", "fresh", f.ts(NOW - DAY))]
    )
    code, out = run_import(home, older)
    assert code == 0
    assert "slack: fetched 1" in out
    rows = query(home, monkeypatch, "SELECT COUNT(*) FROM source_items")
    assert rows[0][0] == 7
    assert query(home, monkeypatch, "SELECT COUNT(*) FROM source_item_revisions")[0][0] == 7


def test_only_read_calls_reach_slack(home, older):
    run_import(home, older)
    calls = CallLog(home / "workspaces" / "work").read()
    slack = [c for c in calls if c["engine"] == "slack"]
    assert slack and {c["method"] for c in slack} <= READ_CALLS
    assert not [c for c in slack if c["args"].get("channel") == "C002"]


def test_paging_beyond_200_for_history_and_replies(tmp_path, home, monkeypatch):
    env = make_env(tmp_path, home, "slack_history_paged")
    code, out = run_import(home, env)
    assert code == 0
    assert query(home, monkeypatch, "SELECT COUNT(*) FROM source_items")[0][0] == 450 + 1 + 230


def test_malformed_message_fails_that_item_only(home, older, monkeypatch):
    page = home.parent / "fixtures" / "slack" / "history" / "C001" / "page-0.json"
    data = json.loads(page.read_text())
    data["messages"].append({"type": "message", "user": "U001", "text": "no timestamp"})
    page.write_text(json.dumps(data))
    code, out = run_import(home, older)
    assert code == 1
    assert "failed 1" in out and "fetched 6" in out
    failed = query(
        home, monkeypatch, "SELECT stage, error FROM import_item_stages WHERE status = 'failed'"
    )
    assert failed[0][0] == "fetch" and "ts" in failed[0][1]
    assert query(home, monkeypatch, "SELECT COUNT(*) FROM source_items")[0][0] == 6


def import_twice(home, env):
    assert run_import(home, env)[0] == 0
    return run_import(home, env)


def test_edited_message_gets_a_new_revision_and_only_it(home, tmp_path):
    env = make_env(tmp_path, home, "slack_edited_message")
    code, out = import_twice(home, env)
    assert code == 0 and "slack: fetched 1" in out
    revisions = [show(home, f"slack:C001/{f.ts(NOW - 2 * DAY + n)}")["revisions"] for n in range(3)]
    assert [len(r) for r in revisions] == [1, 2, 1]
    assert [json.loads(r["content"])["text"] for r in revisions[1]] == ["second", "second (edited)"]


def test_deletion_inside_recheck_window_marks_gone_and_keeps_content(home, tmp_path):
    env = make_env(tmp_path, home, "slack_deleted_message")
    import_twice(home, env)
    recent = show(home, f"slack:C001/{f.ts(NOW - 2 * DAY)}")
    assert recent["flags"]["gone_from_source"] is True
    assert json.loads(recent["revisions"][0]["content"])["text"] == "deleted recently"
    assert show(home, f"slack:C001/{f.ts(NOW - 3 * DAY)}")["flags"]["gone_from_source"] is False


def test_deletion_older_than_recheck_window_is_not_noticed(home, tmp_path):
    env = make_env(tmp_path, home, "slack_deleted_message")
    import_twice(home, env)
    # 20 days old: inside the first-run window, outside the 7-day re-check.
    assert show(home, f"slack:C001/{f.ts(NOW - 20 * DAY)}")["flags"]["gone_from_source"] is False


def test_unpicked_conversation_keeps_items_and_is_not_fetched_again(home, older, monkeypatch):
    run_import(home, older)
    proc = popen_librarian_tty(["slack", "pick"], home, older)
    os.write(proc.pty_master, b"1\n\n")  # toggles the first listed conversation, C001, off
    assert finish_tty(proc)[0] == 0
    CallLog(home / "workspaces" / "work").path.unlink()
    run_import(home, older)
    assert query(home, monkeypatch, "SELECT COUNT(*) FROM source_items")[0][0] == 6
    assert not [
        c
        for c in CallLog(home / "workspaces" / "work").read()
        if c["method"] in ("history", "replies")
    ]


def run_import_older(home, env, answer):
    proc = popen_librarian_tty(["slack", "import-older", "atlas-dev"], home, env)
    os.write(proc.pty_master, answer)
    code, out = finish_tty(proc)
    return code, out.replace("\r", "")


def test_import_older_prints_count_first_and_fetches_only_after_yes(home, older, monkeypatch):
    run_import(home, older)
    code, out = run_import_older(home, older, b"n\n")
    assert code == 0 and "3 messages older than 30 days" in out and "nothing fetched" in out
    assert query(home, monkeypatch, "SELECT COUNT(*) FROM source_items")[0][0] == 6
    code, out = run_import_older(home, older, b"y\n")
    assert code == 0 and "slack: fetched 3" in out
    assert query(home, monkeypatch, "SELECT COUNT(*) FROM source_items")[0][0] == 9
    run_import(home, older)
    assert query(home, monkeypatch, "SELECT COUNT(*) FROM source_items")[0][0] == 9


def test_import_older_refuses_without_a_terminal(home, older):
    result = run_librarian(["slack", "import-older", "atlas-dev"], home, env=older)
    assert result.returncode != 0 and "needs a terminal" in result.stderr
