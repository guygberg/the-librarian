import json
import os

import pytest

from fixtures.scenarios import people_aliases as p
from librarian import paths
from librarian.importer.lock import workspace_lock
from support.api import Api
from support.cli import finish_tty, popen_librarian_tty, run_librarian
from support.recordings import make_env, run_import
from support.serve import spawn

CONVERSATION = "C001"


@pytest.fixture
def api(tmp_path, home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    me_names = ", ".join(json.dumps(n, ensure_ascii=False) for n in p.ME_NAMES)
    env, _ = make_env(tmp_path, home, "people_aliases", f"me_names = [{me_names}]\n")
    env["LIBRARIAN_NOW"] = str(p.NOW)
    (home / "workspaces" / "work").mkdir(parents=True, exist_ok=True)
    (home / "workspaces" / "work" / "channels.json").write_text(
        json.dumps({"picked": [CONVERSATION]})
    )
    code, out = run_import(home, env)
    assert code == 0, out
    proc, served = spawn(home, "--port", "0", env=env)
    yield Api(served, home, env)
    proc.terminate()
    proc.wait(timeout=10)
    proc.stdout.close()


def forget_in_pty(api, answers, conversation=CONVERSATION):
    proc = popen_librarian_tty(["forget", conversation], api.home, api.env)
    os.write(proc.pty_master, "".join(a + "\n" for a in answers).encode())
    return finish_tty(proc)


SLACK_RECORDS = (
    "SELECT COUNT(*) FROM records WHERE id IN"
    " (SELECT record_id FROM evidence WHERE locator LIKE 'slack:%')"
)


def counts(api):
    """The conversation's footprint; the scenario's recording stays outside it."""
    like = f"{CONVERSATION}/%"
    return {
        "items": api.sql("SELECT COUNT(*) FROM source_items WHERE stable_id LIKE ?", like)[0][0],
        "revisions": api.sql(
            "SELECT COUNT(*) FROM source_item_revisions WHERE source_item_id IN"
            " (SELECT id FROM source_items WHERE stable_id LIKE ?)",
            like,
        )[0][0],
        "search": api.sql("SELECT COUNT(*) FROM source_search WHERE stable_id LIKE ?", like)[0][0],
        "records": api.sql(SLACK_RECORDS)[0][0],
        "evidence": api.sql("SELECT COUNT(*) FROM evidence WHERE locator LIKE 'slack:%'")[0][0],
    }


def test_wrong_confirmation_deletes_nothing_and_right_one_deletes_items_and_records(api):
    before = counts(api)
    assert before["records"] and before["items"]
    other = api.sql(
        "SELECT COUNT(*) FROM source_items WHERE stable_id NOT LIKE ?", f"{CONVERSATION}/%"
    )
    title = api.sql(
        "SELECT title FROM records WHERE id IN"
        " (SELECT record_id FROM evidence WHERE locator LIKE 'slack:%')"
    )[0][0]
    record_id = api.record(title)

    code, out = forget_in_pty(api, ["nope"])
    assert code == 1 and "nothing deleted" in out
    assert counts(api) == before

    code, out = forget_in_pty(api, [CONVERSATION])
    assert code == 0, out
    assert counts(api) == dict.fromkeys(before, 0)
    assert (
        api.sql("SELECT COUNT(*) FROM source_items WHERE stable_id NOT LIKE ?", f"{CONVERSATION}/%")
        == other
    )
    assert api.sql("SELECT conversation_id FROM slack_picks") == []
    shown = run_librarian(["show", str(record_id)], api.home, env=api.env)
    assert "not_found" in shown.stdout
    [event] = [
        e
        for e in api.cli("changes", TZ="UTC")["person_events"]
        if e["event"] == "forget_conversation"
    ]
    assert event["record_id"] is None and event["change"]["conversation"] == CONVERSATION
    assert (
        event["change"]["items"] == before["items"]
        and event["change"]["records"] == before["records"]
    )


def test_record_with_evidence_elsewhere_keeps_it_and_loses_only_the_removed_items(api):
    title = api.sql(
        "SELECT title FROM records WHERE id IN"
        " (SELECT record_id FROM evidence WHERE locator LIKE 'slack:%')"
    )[0][0]
    record_id = api.record(title)
    conn = api.conn()
    with conn:
        conn.execute(
            "INSERT INTO source_items (workspace, source, stable_id, created_at)"
            " VALUES ('work', 'slack', 'C002/1.0', 't')"
        )
        item = conn.execute("SELECT id FROM source_items WHERE stable_id = 'C002/1.0'").fetchone()[
            0
        ]
        conn.execute(
            "INSERT INTO source_item_revisions"
            " (workspace, source_item_id, revision, content_hash, content, fetched_at)"
            " VALUES ('work', ?, 1, 'h', '{}', 't')",
            (item,),
        )
        revision = conn.execute(
            "SELECT id FROM source_item_revisions WHERE source_item_id = ?", (item,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO evidence"
            " (workspace, record_id, revision_id, locator, quote, role, retrieved_at)"
            " VALUES ('work', ?, ?, 'slack:C002/1.0', 'q', 'supports', 't')",
            (record_id, revision),
        )
    conn.close()

    code, out = forget_in_pty(api, [CONVERSATION])
    assert code == 0, out
    assert api.sql("SELECT locator FROM evidence WHERE record_id = ?", record_id) == [
        ("slack:C002/1.0",)
    ]
    assert api.sql("SELECT COUNT(*) FROM records WHERE id = ?", record_id) == [(1,)]
    assert api.sql("SELECT stable_id FROM source_items WHERE stable_id LIKE 'C00%'") == [
        ("C002/1.0",)
    ]


def test_refuses_without_a_terminal(api):
    before = counts(api)
    out = run_librarian(["forget", CONVERSATION], api.home, env=api.env)
    assert out.returncode != 0 and "terminal" in out.stdout + out.stderr
    assert counts(api) == before


def test_refuses_while_an_import_holds_the_lock(api):
    before = counts(api)
    with workspace_lock(paths.workspace_dir("work")):
        code, out = forget_in_pty(api, [CONVERSATION])
        status, body = api.post("/api/forget", {"conversation": CONVERSATION, "confirm": True})
    assert code == 1 and "import is running" in out
    assert status == 409
    assert counts(api) == before


def test_http_needs_the_confirm_parameter_and_the_token(api):
    before = counts(api)
    assert api.post("/api/forget", {"conversation": CONVERSATION})[0] == 400
    assert api.post("/api/forget", {"conversation": CONVERSATION, "confirm": "yes"})[0] == 400
    status, _ = api.post(
        "/api/forget",
        {"conversation": CONVERSATION, "confirm": True},
        headers={"Content-Type": "application/json"},
    )
    assert status in (401, 403)
    assert counts(api) == before

    status, body = api.post("/api/forget", {"conversation": CONVERSATION, "confirm": True})
    assert status == 200 and body["records"] == before["records"]
    assert counts(api)["records"] == 0 and body["items"] == before["items"]
