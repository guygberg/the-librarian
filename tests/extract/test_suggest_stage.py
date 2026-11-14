import json
import sqlite3

import pytest

from librarian import config, db, paths
from librarian.extract import suggest_stage
from librarian.extract.runs import RunMeta
from librarian.importer.lock import workspace_lock
from support.cli import run_librarian

WS = "work"
DANA = "I will send the rollout plan by Friday."


class Stub:
    """A suggester answering per unit key; a Python exception in the answer is raised."""

    def __init__(self, answers=None, prompt="p1"):
        self.answers = answers or {}
        self.prompt = prompt
        self.calls: list[str] = []

    @property
    def meta(self):
        return RunMeta("stub-model", "0", self.prompt)

    def extract(self, unit_key, unit_text, candidates):
        self.calls.append(unit_key)
        answer = self.answers.get(unit_key, {"suggestions": []})
        if isinstance(answer, BaseException):
            raise answer
        return answer if isinstance(answer, str) else json.dumps(answer)


def tag(ref="t1", title="Rollout", locator="slack:C1/1760000000.0#1"):
    return {
        "ref": ref,
        "kind": "new_tag",
        "title": title,
        "confidence": 90,
        "basis": "stated",
        "reasoning": "Named.",
        "evidence": [{"locator": locator, "quote": DANA}],
    }


@pytest.fixture
def conn(home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    c = db.connect_rw(WS)
    c.execute("INSERT INTO persons (workspace, name, created_at) VALUES ('work', 'Dana', 'x')")
    yield c
    c.close()


def add_item(conn, channel, ts, text=DANA, workspace=WS):
    item_id = conn.execute(
        "INSERT INTO source_items (workspace, source, stable_id, created_at)"
        " VALUES (?, 'slack', ?, 'x')",
        (workspace, f"{channel}/{ts}"),
    ).lastrowid
    conn.execute(
        "INSERT INTO source_item_revisions (workspace, source_item_id, revision, content_hash,"
        " content, fetched_at) VALUES (?, ?, 1, 'h', ?, 'x')",
        (workspace, item_id, json.dumps({"ts": ts, "user": "Dana", "text": text})),
    )


def key(channel):
    return f"slack-day-{channel}-2025-10-09"


def analyse(conn, suggester, max_calls=10, dry_run=False):
    return suggest_stage.analyse(conn, WS, suggester, max_calls, config.load(), dry_run)


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def snapshot(conn):
    tables = ("records", "persons", "links", "evidence", "suggestions", "suggestion_units",
              "extraction_runs", "extracted_units")  # fmt: skip
    return {t: conn.execute(f"SELECT * FROM {t}").fetchall() for t in tables}


@pytest.fixture
def two_units(conn):
    add_item(conn, "C1", "1760000000.0")
    add_item(conn, "C2", "1760000100.0")


def test_unchanged_units_are_not_resent(conn, two_units):
    first = Stub()
    assert analyse(conn, first).sent == 2
    second = Stub()
    counts = analyse(conn, second)
    assert (counts.eligible, counts.sent, second.calls) == (0, 0, [])


def test_changed_text_prompt_or_schema_is_resent(conn, two_units, monkeypatch):
    analyse(conn, Stub())
    add_item(conn, "C1", "1760000001.0", "something new")
    again = Stub()
    assert analyse(conn, again).sent == 1 and again.calls == [key("C1")]

    reprompted = Stub(prompt="p2")
    assert analyse(conn, reprompted).sent == 2

    monkeypatch.setattr(suggest_stage.schema, "suggest_schema_hash", lambda: "other")
    assert analyse(conn, Stub(prompt="p2")).sent == 2


def test_empty_answer_succeeds_and_is_not_retried(conn, two_units):
    counts = analyse(conn, Stub())
    assert (counts.succeeded, counts.empty, counts.created, counts.failed) == (2, 2, 0, 0)
    assert analyse(conn, Stub()).eligible == 0


def test_failure_is_retried_and_keeps_existing_suggestions(conn, two_units):
    ok = Stub({key("C1"): {"suggestions": [tag()]}})
    analyse(conn, ok)
    add_item(conn, "C1", "1760000200.0", "changed")  # now the newest unit
    bad = Stub({key("C1"): "{not json"})
    counts = analyse(conn, bad, max_calls=1)
    assert (counts.sent, counts.failed, counts.succeeded) == (1, 1, 0)
    assert count(conn, "suggestions") == 1
    status = conn.execute(
        "SELECT status FROM suggestion_units WHERE unit_key = ?", (key("C1"),)
    ).fetchone()[0]
    assert status == "failed"
    retry = Stub()
    assert analyse(conn, retry).sent == 1 and retry.calls == [key("C1")]
    assert conn.execute("SELECT DISTINCT status FROM suggestion_units").fetchall() == [
        ("succeeded",)
    ]


def test_interruption_leaves_no_false_success(conn, two_units):
    stub = Stub({key("C2"): {"suggestions": []}, key("C1"): KeyboardInterrupt()})
    with pytest.raises(KeyboardInterrupt):
        analyse(conn, stub)
    done = conn.execute("SELECT unit_key FROM suggestion_units").fetchall()
    assert len(done) == 1  # the unit finished before the interruption keeps its success
    assert analyse(conn, Stub()).sent == 1


def test_storing_is_atomic(conn, two_units, monkeypatch):
    def boom(*a, **k):
        raise sqlite3.OperationalError("disk")

    monkeypatch.setattr(suggest_stage, "_insert", boom)
    with pytest.raises(sqlite3.OperationalError):
        analyse(conn, Stub({key("C2"): {"suggestions": [tag(locator="slack:C2/1760000100.0#1")]}}))
    assert count(conn, "suggestions") == 0 and count(conn, "suggestion_units") == 0


def test_call_cap_defers_and_resumes_newest_first(conn, two_units):
    first = Stub()
    counts = analyse(conn, first, max_calls=1)
    assert (counts.eligible, counts.sent, counts.deferred) == (2, 1, 1)
    assert first.calls == [key("C2")]  # the newest unit
    rest = Stub()
    assert analyse(conn, rest, max_calls=1).sent == 1 and rest.calls == [key("C1")]


def test_stored_batch_has_evidence_one_created_event_and_trace(conn, two_units):
    stub = Stub({key("C1"): {"suggestions": [tag(), tag("t2", "Rollout")]}})
    counts = analyse(conn, stub)
    assert counts.created == 1  # the duplicate proposal is stored once
    assert count(conn, "suggestion_evidence") == 1
    events = conn.execute("SELECT event FROM suggestion_events").fetchall()
    assert events == [("created",)]
    run_id, purpose = conn.execute(
        "SELECT s.run_id, r.purpose FROM suggestions s JOIN extraction_runs r ON r.id = s.run_id"
    ).fetchone()
    assert purpose == "suggestions" and run_id
    assert analyse(conn, Stub(), max_calls=0).sent == 0


def test_analysis_leaves_records_tags_persons_links_unchanged(conn, two_units):
    before = {k: v for k, v in snapshot(conn).items() if k in ("records", "persons", "links")}
    analyse(conn, Stub({key("C1"): {"suggestions": [tag()]}}))
    after = snapshot(conn)
    assert {k: after[k] for k in before} == before
    assert after["extracted_units"] == []


def test_dry_run_has_no_calls_and_no_writes(conn, two_units):
    stub = Stub()
    before = snapshot(conn)
    counts = analyse(conn, stub, max_calls=1, dry_run=True)
    assert (counts.eligible, counts.deferred, counts.sent, stub.calls) == (2, 1, 0, [])
    assert snapshot(conn) == before


def test_other_workspace_is_never_read(conn):
    add_item(conn, "C1", "1760000000.0", workspace="other")
    stub = Stub()
    assert analyse(conn, stub).eligible == 0


@pytest.fixture
def cli(home, tmp_path, conn, two_units):
    fixtures = tmp_path / "fixtures"
    (fixtures / "suggestions").mkdir(parents=True)
    (home / "config.toml").write_text('account_type = "team"\nusage_rules_confirmed = true\n')
    conn.close()
    env = {"LIBRARIAN_ENGINES": "fake", "LIBRARIAN_FIXTURES": str(fixtures)}
    return lambda *args: run_librarian(["suggest", *args], home, env=env)


def test_cli_dry_run_then_run_prints_deterministic_counts(cli, home):
    out = cli("--dry-run", "--max-calls", "1")
    assert out.stdout.strip() == "dry run: eligible 2, deferred 1, calls 1, none sent"
    out = cli("--max-calls", "1")
    assert out.returncode == 0, out.stderr
    assert out.stdout.splitlines()[0] == (
        "suggest: eligible 2, sent 1, succeeded 1, failed 0, deferred 1, created 0, empty 1"
    )


def test_cli_refuses_without_the_no_training_gate(cli, home):
    (home / "config.toml").write_text('account_type = "pro"\nusage_rules_confirmed = true\n')
    out = cli()
    assert out.returncode == 1 and "suggest skipped" in out.stdout


def test_cli_stops_when_another_run_holds_the_lock(cli, home):
    with workspace_lock(paths.workspace_dir(WS)):
        out = cli()
    assert out.returncode == 1 and "another import or suggest run is active" in out.stdout
