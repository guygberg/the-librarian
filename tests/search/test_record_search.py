import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "slack"))
from test_fetch import make_env, run_import  # noqa: E402

from support.cli import run_librarian  # noqa: E402
from support.serve import spawn  # noqa: E402


@pytest.fixture
def world(tmp_path, home):
    """The Hebrew Slack fixture imported, plus Records and a person written straight into the database."""
    env = make_env(tmp_path, home, "slack_hebrew")
    assert run_import(home, env)[0] == 0
    conn = sqlite3.connect(next(home.rglob("*.db")))
    with conn:
        revision = conn.execute("SELECT id FROM source_item_revisions LIMIT 1").fetchone()[0]

        def record(kind, title, body=""):
            return conn.execute(
                "INSERT INTO records (workspace, kind, title, body, created_at, updated_at)"
                " VALUES ('work', ?, ?, ?, 'x', 'x')",
                (kind, title, body),
            ).lastrowid

        decision = record("decision", "דחינו את ההשקה")
        project = record("project", "Billing cleanup")
        conn.execute("INSERT INTO project_aliases VALUES ('work', ?, 'ניקוי חשבוניות')", (project,))
        conn.execute(
            "INSERT INTO evidence (workspace, record_id, revision_id, locator, quote, role, retrieved_at)"
            " VALUES ('work', ?, ?, 'slack:C001/1.0', 'נדחה לשבוע הבא', 'supports', 'x')",
            (decision, revision),
        )
        person = conn.execute("INSERT INTO persons (workspace, name, created_at) VALUES ('work', 'Noa Zamir', 'x')").lastrowid
        conn.execute("INSERT INTO aliases (workspace, person_id, alias) VALUES ('work', ?, 'נועה')", (person,))
        meeting = record("action_item", "סיכום הפגישה")
    return home, {"decision": decision, "project": project, "person": person, "meeting": meeting}


def cli(home, query):
    out = run_librarian(["search", query], home)
    assert out.returncode == 0, out.stdout
    return json.loads(out.stdout)


def test_records_come_before_passages_and_hebrew_prefixes_match_both(world):
    home, ids = world
    answer = cli(home, "הפגישה")
    assert [r["id"] for r in answer["records"]] == [ids["meeting"]]
    assert answer["evidence"] and all(e["record_id"] is None for e in answer["evidence"])
    keys = list(answer)
    assert keys.index("records") < keys.index("evidence")


def test_record_evidence_quotes_are_searchable_and_listed_before_passages(world):
    home, ids = world
    answer = cli(home, "שבוע")
    assert [r["id"] for r in answer["records"]] == [ids["decision"]]
    assert answer["evidence"][0]["record_id"] == ids["decision"] and answer["evidence"][0]["locator"] == "slack:C001/1.0"


def test_projects_by_alias_and_people_by_alias_or_name(world):
    home, ids = world
    assert [r["id"] for r in cli(home, "חשבוניות")["records"]] == [ids["project"]]
    for query in ("לנועה", "zamir"):
        [person] = cli(home, query)["people"]
        assert person["person_id"] == ids["person"] and person["aliases"] == ["נועה"]
    assert cli(home, "nonexistent")["people"] == []


def test_the_http_route_returns_what_the_command_returns(world):
    home, _ = world
    proc, served = spawn(home, "--port", "0")
    try:
        resp, data = served.request("GET", "/api/search?q=%D7%94%D7%A4%D7%92%D7%99%D7%A9%D7%94", {"X-Librarian-Token": served.token()})
        assert resp.status == 200
        assert json.loads(data) == cli(home, "הפגישה")
        assert served.request("GET", "/api/search", {"X-Librarian-Token": served.token()})[0].status == 400
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        proc.stdout.close()
