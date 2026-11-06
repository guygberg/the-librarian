import json
import sqlite3
import time

import pytest
from fixtures.scenarios import payments_cutover as payments
from support.cli import run_librarian
from support.jsonschema_lite import errors
from support.recordings import make_env, run_import

STR = {"type": "string"}
RECORD = {
    "type": "object",
    "required": ["id", "kind", "title", "lifecycle"],
    "properties": {"id": {"type": "integer"}, "kind": STR, "title": STR, "lifecycle": STR},
}
EVIDENCE = {
    "type": "object",
    "required": ["record_id", "source", "locator", "quote", "role"],
    "properties": {"source": STR, "locator": STR, "quote": STR, "role": STR},
}
ENVELOPE = {
    "type": "object",
    "required": ["warnings", "resolved", "records", "evidence", "freshness"],
    "properties": {
        "warnings": {"type": "array", "items": {"type": "object", "required": ["code", "message"]}},
        "resolved": {"type": "object", "required": ["project", "baseline"]},
        "records": {"type": "array", "items": RECORD},
        "evidence": {"type": "array", "items": EVIDENCE},
        "freshness": {
            "type": "object",
            "required": ["last_import_finished_at", "sources"],
            "properties": {"sources": {"type": "object"}},
        },
    },
}


@pytest.fixture
def world(tmp_path, home, monkeypatch):
    """`world(config, asked_at)` imports payments-cutover once; the env to ask with is returned. The import runs at
    the scenario's own time, since Slack history older than that is not fetched."""
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))

    def make(config="", asked_at=payments.NOW):
        env, _ = make_env(tmp_path, home, "payments-cutover", config)
        env["LIBRARIAN_NOW"] = str(payments.NOW)
        (home / "workspaces" / "work").mkdir(parents=True, exist_ok=True)
        (home / "workspaces" / "work" / "channels.json").write_text(json.dumps({"picked": ["C001"]}))
        code, out = run_import(home, env)
        assert code == 0, out
        return {**env, "LIBRARIAN_NOW": str(asked_at)}

    return make


def ask(home, env, *args):
    out = run_librarian(list(args), home, env=env)
    assert out.returncode == 0, out.stdout
    return json.loads(out.stdout)


def test_every_answer_command_returns_the_envelope(world, home):
    env = world()
    slack_locator = ask(home, env, "search", "webhook")["evidence"][0]["locator"]
    answers = {
        "open-items": ask(home, env, "open-items"),
        "project": ask(home, env, "project", "payments"),
        "unknown project": ask(home, env, "project", "zzz"),
        "search": ask(home, env, "search", "webhook"),
        "show record": ask(home, env, "show", str(payments.PROJECT_ID)),
        "show source item": ask(home, env, "show", slack_locator),
    }
    for name, answer in answers.items():
        assert errors(answer, ENVELOPE) == [], name
        assert list(answer)[0] == "warnings", name


def test_project_facts_each_carry_an_evidence_locator(world, home):
    env = world()
    answer = ask(home, env, "project", "payments")
    assert answer["resolved"]["project"] == {"id": payments.PROJECT_ID, "name": payments.PROJECT}
    assert answer["records"] and all(
        any(e["record_id"] == r["id"] and e["locator"] and e["quote"] and e["role"] for e in answer["evidence"])
        for r in answer["records"]
    )
    facts = answer["project"]
    assert facts["status"]["value"] == "open" and facts["status"]["evidence"]
    assert facts["latest_decision"]["title"] == payments.NOV_25 and facts["latest_decision"]["evidence"]
    assert facts["main_blocker"]["title"] == payments.BLOCKER and facts["main_blocker"]["evidence"]
    assert [o["name"] for o in facts["owners"]] == ["Raz Peretz"] and facts["owners"][0]["evidence"]
    assert facts["deadlines"] == "not found"


def test_basis_stale_and_contradictions_are_in_the_json(world, home):
    env = world()
    records = {r["title"]: r for r in ask(home, env, "project", "payments")["records"]}
    for record in records.values():
        assert "basis" in record and "stale" in record and "contradictions" in record
    assert [c["title"] for c in records[payments.NOV_18]["contradictions"]] == [payments.NOV_25]
    assert [c["title"] for c in records[payments.NOV_25]["contradictions"]] == [payments.NOV_18]


def test_an_unknown_name_returns_no_candidates_and_a_clear_winner_is_named(world, home):
    env = world()
    nothing = ask(home, env, "project", "zzz")
    assert nothing["resolved"] == {"project": None, "baseline": None} and nothing["candidates"] == []
    assert nothing["warnings"][0]["code"] == "project_not_found"
    assert ask(home, env, "project", "Payments Migration")["resolved"]["project"]["id"] == payments.PROJECT_ID


def test_two_close_projects_are_candidates_not_a_guess(world, home):
    env = world()
    db = sqlite3.connect(next(home.rglob("*.db")))
    with db:
        db.execute(
            "INSERT INTO records (workspace, kind, title, created_at, updated_at)"
            " SELECT workspace, kind, 'Payments review', created_at, updated_at FROM records WHERE id = ?",
            (payments.PROJECT_ID,),
        )
    answer = ask(home, env, "project", "payments")
    assert answer["resolved"] == {"project": None, "baseline": None}
    assert answer["warnings"][0]["code"] == "project_ambiguous"
    assert [c["name"] for c in answer["candidates"]] == [payments.PROJECT, "Payments review"]
    assert {"id", "name", "parent", "last_activity"} <= answer["candidates"][0].keys()


def test_a_never_imported_source_leads_the_answer(world, home):
    env = world()
    for command in (["open-items"], ["project", "payments"], ["search", "webhook"]):
        warning = ask(home, env, *command)["warnings"][0]
        assert (warning["code"], warning["source"]) == ("source_never_imported", "session")


def test_an_overdue_import_leads_the_answer(world, home):
    env = world('import_sources = ["slack"]\nsource_overdue_days = 7\n', asked_at=time.time() + 30 * 86_400)
    answer = ask(home, env, "open-items")
    assert (answer["warnings"][0]["code"], answer["warnings"][0]["source"]) == ("source_overdue", "slack")
    assert answer["freshness"]["sources"]["slack"]["overdue"] is True


def test_a_recent_import_has_no_warning(world, home):
    env = world('import_sources = ["slack"]\n', asked_at=time.time())
    assert ask(home, env, "open-items")["warnings"] == []
