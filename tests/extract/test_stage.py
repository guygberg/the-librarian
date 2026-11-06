import json

import pytest

from fixtures import formats as f
from fixtures.build import build
from fixtures.scenarios import extractor_failure as failure
from librarian import db, engines, store
from librarian.extract import stage as extract
from librarian.fakes.calllog import CallLog
from support.cli import finish_tty, popen_librarian_tty, run_librarian

T0 = 1_760_000_000  # the base fixture's clock
NOW = T0 + 86_400
THREAD_ROOT = f.ts(T0 + 100 * 60)
THREAD_REPLY = THREAD_ROOT  # the base fixture marks no replies, so only the root is fetched
THREAD_KEY = f"slack-thread-C001-{THREAD_ROOT}"
DAY_KEY = "slack-day-C001-2025-10-09"


def make_env(tmp_path, home, scenario, now):
    fixtures = tmp_path / "fixtures"
    build(fixtures, scenario)
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text('account_type = "team"\nusage_rules_confirmed = true\n')
    ws = home / "workspaces" / "work"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "channels.json").write_text(json.dumps({"picked": ["C001"]}))
    return {"LIBRARIAN_ENGINES": "fake", "LIBRARIAN_FIXTURES": str(fixtures), "LIBRARIAN_NOW": str(now)}, fixtures


def run_import(home, env):
    code, out = finish_tty(popen_librarian_tty(["import"], home, env))
    return code, out.replace("\r", "")


def canned(fixtures, key, **body):
    folder = fixtures / "extraction"
    folder.mkdir(exist_ok=True)
    (folder / f"{key}.json").write_text(json.dumps(body))


def show(home, record_id):
    out = run_librarian(["show", str(record_id)], home)
    assert out.returncode == 0, out.stdout
    return json.loads(out.stdout)


def thread_result():
    def evidence(locator, quote, **extra):
        return [{"locator": locator, "quote": quote, "role": "supports", **extra}]

    base = {"match": {"decision": "new"}, "lifecycle": "open", "basis": "stated"}
    return {
        "records": [
            {**base, "ref": "p", "kind": "project", "title": "Atlas",
             "evidence": evidence(f"slack:C001/{THREAD_ROOT}", "Should Atlas use SQLite per workspace?")},
            {**base, "ref": "d", "kind": "decision", "title": "SQLite with FTS5", "lifecycle": "done",
             "reasoning": "one file per workspace", "links": [{"type": "belongs_to", "to": {"ref": "p"}}],
             "evidence": evidence(f"slack:C001/{THREAD_REPLY}#1", "use SQLite per workspace")},
            {**base, "ref": "a", "kind": "action_item", "title": "Draft the schema", "commitment": "request",
             "owner": {"slack_user": "U003"}, "stated_deadline": "2026-12-01",
             "evidence": evidence(f"slack:C001/{THREAD_REPLY}", "Should Atlas use SQLite", gloss="Priya agrees")},
        ]
    }


@pytest.fixture
def base(tmp_path, home):
    return make_env(tmp_path, home, "base", NOW)


def test_import_stores_records_each_with_located_evidence(home, base):
    env, fixtures = base
    canned(fixtures, THREAD_KEY, result=thread_result())

    code, out = run_import(home, env)

    assert code == 0, out
    project, decision, action = show(home, 1), show(home, 2), show(home, 3)
    assert (project["kind"], project["title"], project["lifecycle"], project["basis"]) == (
        "project", "Atlas", "open", "inferred")  # a project Claude creates waits for the person to confirm it
    assert decision["projects"] == [{"id": 1, "title": "Atlas"}]
    assert decision["reasoning"] == "one file per workspace"
    assert (action["commitment"], action["owner"], action["stated_deadline"]) == ("request", "Priya Shah", "2026-12-01")
    [cited] = action["evidence"]
    assert cited.items() >= {
        "locator": f"slack:C001/{THREAD_REPLY}", "quote": "Should Atlas use SQLite", "role": "supports", "gloss": "Priya agrees"
    }.items()
    for record in (project, decision, action):
        assert record["evidence"] and all({"locator", "quote", "role"} <= e.keys() for e in record["evidence"])
    assert run_librarian(["show", "99"], home).returncode == 1


def test_rejected_pieces_are_logged_and_the_good_remainder_is_stored(home, base):
    env, fixtures = base
    good = {"match": {"decision": "new"}, "lifecycle": "open", "basis": "stated", "kind": "decision"}
    note = f"slack:C001/{f.ts(T0 + 3 * 60)}"
    result = {
        "records": [
            {**good, "ref": "ok", "title": "Kept", "links": [{"type": "related_to", "to": {"ref": "ghost"}}],
             "evidence": [{"locator": note, "quote": "Atlas status note 3", "role": "supports"}]},
            {**good, "ref": "invented", "title": "Dropped quote",
             "evidence": [{"locator": note, "quote": "never said this", "role": "supports"}]},
            {**good, "ref": "badid", "title": "Dropped id", "match": {"decision": "same", "id": 99},
             "evidence": [{"locator": note, "quote": "Atlas status note 3", "role": "supports"}]},
        ]
    }
    canned(fixtures, DAY_KEY, result=result)

    code, _ = run_import(home, env)

    assert code == 0
    assert show(home, 1)["title"] == "Kept" and show(home, 1)["links"] == []
    assert run_librarian(["show", "2"], home).returncode == 1
    text = run_librarian(["runs"], home).stdout
    for reason in ("quote_not_found", "no_evidence", "unknown_id", "bad_link_end"):
        assert reason in text


def test_failed_unit_is_reported_and_retried_alone(tmp_path, home):
    env, fixtures = make_env(tmp_path, home, "extractor_failure", failure.NOW)

    code, out = run_import(home, env)

    assert code == 1
    assert f"failed at extract (2 items): ExtractionError: {failure.BROKEN}" in out
    assert show(home, 1)["title"] == "Where is the second loose message from?"
    assert f"{failure.DAY_KEY}\t" in run_librarian(["runs"], home).stdout

    log = CallLog(home / "workspaces" / "work")
    calls_before = len(log.read())
    canned(fixtures, failure.THREAD_KEY, result={"records": []})
    code, out = run_import(home, env)

    assert code == 0, out
    extracted = [c["args"]["unit_key"] for c in log.read()[calls_before:] if c["engine"] == "extractor"]
    assert extracted == [failure.THREAD_KEY]


def test_units_group_threads_channel_days_and_transcript_windows(home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    monkeypatch.setenv("LIBRARIAN_ENGINES", "fake")
    fixtures = home / "fixtures"
    fixtures.mkdir(parents=True)
    monkeypatch.setenv("LIBRARIAN_FIXTURES", str(fixtures))
    conn = db.connect_rw("work")

    def put(source, stable_id, **content):
        store.upsert(conn, "work", source, stable_id, json.dumps(content), origin_name=content.get("path", ""))

    day = 1_700_000_000
    put("slack", f"C1/{day}.000000", user="U1", text="root", ts=f"{day}.000000", thread_ts=f"{day}.000000")
    put("slack", f"C1/{day + 1}.000000", user="U2", text="reply", ts=f"{day + 1}.000000", thread_ts=f"{day}.000000")
    put("slack", f"C1/{day + 2}.000000", user="U1", text="loose a", ts=f"{day + 2}.000000")
    put("slack", f"C1/{day + 3}.000000", user="U1", text="loose b", ts=f"{day + 3}.000000")
    for number, start in enumerate(range(0, 40 * 60, 5 * 60), start=1):
        put("drive", f"abc/{number}", segment=number, start=float(start), text=f"words {number}", path="talk.m4a")

    got = extract.stage("work", engines.get_engines().extractor)
    for source, item in [("slack", f"C1/{day}.000000"), ("slack", f"C1/{day + 1}.000000"),
                         ("slack", f"C1/{day + 2}.000000"), ("slack", f"C1/{day + 3}.000000"),
                         ("recording", "talk.m4a")]:
        got.process(conn, source, item)

    keys = [c["args"]["unit_key"] for c in CallLog(db.db_path("work").parent).read()]
    assert sorted(keys) == sorted([
        f"slack-thread-C1-{day}.000000", "slack-day-C1-2023-11-14", "drive-abc-1", "drive-abc-2", "drive-abc-3",
    ])


def extractor_keys(home):
    return [c["args"]["unit_key"] for c in CallLog(home / "workspaces" / "work").read() if c["engine"] == "extractor"]


def import_with(home, env, *flags):
    code, out = finish_tty(popen_librarian_tty(["import", *flags], home, env))
    return code, out.replace("\r", "")


def test_cap_stops_cleanly_newest_first_and_the_next_run_continues(home, base):
    env, _ = base

    code, out = import_with(home, env, "--max-calls", "1")
    assert code == 0, out
    assert extractor_keys(home) == [DAY_KEY]  # its latest message is newer than the thread root
    assert "1 calls made, 1 units remaining" in out

    code, out = import_with(home, env, "--max-calls", "1")
    assert code == 0, out
    assert extractor_keys(home) == [DAY_KEY, THREAD_KEY]
    assert "1 calls made, 0 units remaining" in out


def test_dry_run_counts_the_calls_a_real_run_makes_and_sends_nothing(home, base):
    env, _ = base

    code, out = import_with(home, env, "--dry-run")
    assert code == 0, out
    assert "dry run: 2 extraction calls would be made" in out
    assert extractor_keys(home) == []
    assert run_librarian(["show", "1"], home).returncode == 1

    assert run_import(home, env)[0] == 0
    assert len(extractor_keys(home)) == 2


def test_an_edit_costs_one_call_and_an_unchanged_rerun_none(tmp_path, home):
    env, _ = make_env(tmp_path, home, "slack_edited_message", 1_700_000_000)

    assert run_import(home, env)[0] == 0
    assert len(extractor_keys(home)) == 1

    assert run_import(home, env)[0] == 0  # the second generation carries the edit
    assert len(extractor_keys(home)) == 2

    assert run_import(home, env)[0] == 0
    assert len(extractor_keys(home)) == 2
