import json
import sqlite3

import pytest

from fixtures.scenarios import payments_cutover as payments
from support.recordings import make_env, run_import
from support.serve import spawn

NOW = str(payments.NOW)


class Api:
    def __init__(self, served, home):
        self.served, self.home = served, home

    def get(self, query):
        resp, data = self.served.request("GET", f"/api/graph?{query}", {"X-Librarian-Token": self.served.token()})
        return resp.status, json.loads(data)

    def sql(self, query, *params):
        conn = sqlite3.connect(next(self.home.rglob("*.db")))
        with conn:
            return conn.execute(query, params).fetchall()


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
    yield Api(served, home)
    proc.terminate()
    proc.wait(timeout=10)
    proc.stdout.close()


def hops_of(body):
    return {n["id"]: n["hop"] for n in body["nodes"]}


def test_hops_add_layers_with_distances_and_the_kind_filter_drops_other_kinds(api):
    project = f"record:{payments.PROJECT_ID}"

    status, one = api.get(f"center={project}&hops=1")
    assert status == 200
    assert hops_of(one)[project] == 0
    assert {n["hop"] for n in one["nodes"]} == {0, 1}
    assert f"record:{payments.NOV_18_ID}" in hops_of(one)
    assert {"belongs_to", "blocks"} >= {e["kind"] for e in one["edges"]} >= {"belongs_to"}
    assert all(e["evidence"] for e in one["edges"] if e["from"] == f"record:{payments.NOV_18_ID}")

    _, two = api.get(f"center={project}&hops=2")
    owners = [n for n in two["nodes"] if n["type"] == "person"]
    assert [n["hop"] for n in owners] == [2] and owners[0]["title"] == "Raz Peretz" and "aliases" in owners[0]
    assert "owner" in {e["kind"] for e in two["edges"]}

    _, three = api.get(f"center={project}&hops=3")
    assert max(n["hop"] for n in three["nodes"]) <= 3

    _, only_owner = api.get(f"center={project}&hops=3&kinds=owner")
    assert {e["kind"] for e in only_owner["edges"]} <= {"owner"}
    assert hops_of(only_owner) == {project: 0}


def test_centre_on_a_person_returns_owned_records_and_superseded_records_keep_edges(api):
    [(person,)] = api.sql("SELECT id FROM persons WHERE name = 'Raz Peretz'")
    [(blocker,)] = api.sql("SELECT id FROM records WHERE title = ?", payments.BLOCKER)
    api.sql("UPDATE records SET lifecycle = 'superseded' WHERE id = ?", blocker)

    status, body = api.get(f"center=person:{person}&hops=2")
    assert status == 200
    ids = hops_of(body)
    assert ids[f"record:{blocker}"] == 1
    assert ids[f"record:{payments.PROJECT_ID}"] == 2
    superseded = next(n for n in body["nodes"] if n["id"] == f"record:{blocker}")
    assert superseded["lifecycle"] == "superseded"
    assert [(e["kind"], e["to"]) for e in body["edges"] if e["from"] == superseded["id"] and e["kind"] == "owner"] == [
        ("owner", f"person:{person}")
    ]


@pytest.mark.parametrize(
    "query, status",
    [
        ("center=record:1&hops=0", 400),
        ("center=record:1&hops=4", 400),
        ("center=record:1&hops=x", 400),
        ("center=record:1&kinds=nonsense", 400),
        ("hops=1", 400),
        ("center=record:99999", 404),
        ("center=person:99999", 404),
    ],
)
def test_invalid_requests_return_4xx(api, query, status):
    assert api.get(query)[0] == status
