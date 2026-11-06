import json
import sqlite3

import pytest

from fixtures.scenarios import people_aliases as p
from librarian.link import people, review
from support.cli import run_librarian
from support.recordings import make_env, run_import
from support.serve import spawn

JSON = {"Content-Type": "application/json"}
COLLIDING, NEAR, FIRST_PERSON = "By colliding name", "By near-duplicate name", "By first person"


class Api:
    def __init__(self, served, home, env):
        self.served, self.home, self.env = served, home, env
        self.headers = {**JSON, "X-Librarian-Token": served.token()}

    def call(self, method, path, body=None, headers=None):
        resp, data = self.served.request(method, path, headers or self.headers, json.dumps(body) if body else None)
        return resp.status, json.loads(data)

    def post(self, path, body=None, headers=None):
        return self.call("POST", path, body or {}, headers)

    def review(self):
        return self.call("GET", "/api/review")[1]

    def conn(self):
        return sqlite3.connect(next(self.home.rglob("*.db")))

    def sql(self, query, *params):
        return self.conn().execute(query, params).fetchall()

    def record(self, title):
        return self.sql("SELECT id FROM records WHERE title = ?", title)[0][0]

    def person(self, name):
        return self.sql("SELECT id FROM persons WHERE name = ?", name)[0][0]

    def row(self, title):
        [row] = [r for r in self.review()["rows"] if r["record"]["title"] == title]
        return row

    def show(self, title):
        out = run_librarian(["show", str(self.record(title))], self.home, env=self.env)
        assert out.returncode == 0, out.stdout
        return json.loads(out.stdout)

    def open_items(self):
        out = run_librarian(["open-items"], self.home, env={**self.env, "TZ": "UTC"})
        assert out.returncode == 0, out.stdout
        return {r["title"]: r["group"] for r in json.loads(out.stdout)["records"]}

    def reimport(self):
        code, out = run_import(self.home, self.env)
        assert code == 0, out

    def events(self, name):
        return [e for (e,) in self.sql("SELECT event FROM record_events WHERE event = ?", name)]


@pytest.fixture
def api(tmp_path, home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    me_names = ", ".join(json.dumps(n, ensure_ascii=False) for n in p.ME_NAMES)
    env, _ = make_env(tmp_path, home, "people_aliases", f"me_names = [{me_names}]\n")
    env["LIBRARIAN_NOW"] = str(p.NOW)
    (home / "workspaces" / "work").mkdir(parents=True, exist_ok=True)
    (home / "workspaces" / "work" / "channels.json").write_text(json.dumps({"picked": ["C001"]}))
    code, out = run_import(home, env)
    assert code == 0, out
    proc, served = spawn(home, "--port", "0", env=env)
    yield Api(served, home, env)
    proc.terminate()
    proc.wait(timeout=10)
    proc.stdout.close()


def test_review_rows_carry_both_sides_evidence_and_the_raw_name_and_the_count_matches(api):
    data = api.review()
    assert data["count"] == len(data["rows"]) == 3
    row = api.row(COLLIDING)
    assert (row["kind"], row["mark"], row["raw_name"]) == ("unconfirmed_person", "unconfirmed person", "Dana Cohen")
    assert row["record"]["evidence"]
    assert sorted(c["name"] for c in row["candidates"]) == ["Dana Cohen", "dana  cohen"]
    assert api.row(NEAR)["candidates"] == []


def test_suggestions_stay_out_of_needs_attention(api):
    groups = api.open_items()
    assert groups[COLLIDING] == groups[NEAR] == "other_open"


def test_accepting_saves_the_alias_so_the_name_links_automatically_after_import(api):
    person = api.person("Dana Cohen")
    row = api.row(COLLIDING)
    status, view = api.post(f"/api/review/{row['id']}/accept", {"person_id": person})
    assert (status, view["owner"]) == (200, "Dana Cohen")
    assert "suggested" not in view and api.review()["count"] == 2

    api.reimport()
    assert api.show(COLLIDING)["owner"] == "Dana Cohen" and "suggested" not in api.show(COLLIDING)
    assert api.events("accept_suggestion") == ["accept_suggestion"]
    conn = api.conn()
    assert people.resolve(conn, "work", {"name": "dana cohen"}, False) == (person, None)


def test_accepting_with_no_person_makes_one_named_after_the_alias(api):
    row = api.row(NEAR)
    assert api.post(f"/api/review/{row['id']}/accept")[1]["owner"] == "Dana Cohn"
    assert api.sql("SELECT COUNT(*) FROM persons WHERE name = 'Dana Cohn'") == [(1,)]


def test_rejecting_sticks_through_the_next_import(api):
    row = api.row(NEAR)
    status, view = api.post(f"/api/review/{row['id']}/reject")
    assert (status, "suggested" in view, "owner" in view) == (200, False, False)
    assert api.events("reject_suggestion") == ["reject_suggestion"]

    api.reimport()
    conn = api.conn()
    with conn:
        review.add(conn, "work", review.UNCONFIRMED_PERSON, api.record(NEAR), "owner", "Dana Cohn")
    assert [r["record"]["title"] for r in api.review()["rows"] if r["raw_name"] == "Dana Cohn"] == []


def test_move_alias_reowns_the_record_logs_a_person_event_and_survives_import(api):
    record, old, new = api.record("By id"), api.person("Dana Cohen"), api.person("dana  cohen")
    status, view = api.post(
        "/api/aliases/move", {"alias": "Dana Cohen", "from_person_id": old, "to_person_id": new, "record_id": record}
    )
    assert (status, view["owner"]) == (200, "dana  cohen")
    api.reimport()
    assert api.show("By id")["owner"] == "dana  cohen"
    assert api.events("move_alias") == ["move_alias"]
    assert api.sql("SELECT person_id FROM aliases WHERE alias = 'Dana Cohen'") == [(new,)]


def test_split_alias_moves_it_to_a_new_person_and_survives_import(api):
    record, old = api.record("By id"), api.person("Dana Cohen")
    status, view = api.post(
        "/api/aliases/split", {"alias": "dcohen", "from_person_id": old, "record_id": record, "name": "D. Cohen"}
    )
    assert (status, view["owner"]) == (200, "D. Cohen")
    api.reimport()
    assert api.show("By id")["owner"] == "D. Cohen"
    assert api.events("split") == ["split"]
    assert api.sql("SELECT person_id FROM aliases WHERE alias = 'dcohen'") == [(api.person("D. Cohen"),)]


def test_guards_refuse_without_token_or_with_foreign_origin_and_write_nothing(api):
    row = api.row(NEAR)
    for headers in (JSON, {**api.headers, "Origin": "http://evil.test"}):
        assert api.post(f"/api/review/{row['id']}/reject", headers=headers)[0] == 403
        assert api.post("/api/aliases/split", {"alias": "dcohen"}, headers=headers)[0] == 403
    assert api.review()["count"] == 3
    assert api.sql("SELECT COUNT(*) FROM record_events") == [(0,)]


@pytest.mark.parametrize(
    ("path", "body", "status"),
    [
        ("/api/review/9999/accept", {}, 404),
        ("/api/review/{speaker}/accept", {}, 409),
        ("/api/review/{near}/accept", {"person_id": 9999}, 404),
        ("/api/aliases/move", {"alias": "Dana Cohen", "from_person_id": 1, "to_person_id": 2}, 400),
        ("/api/aliases/split", {"alias": "nobody", "from_person_id": 1, "record_id": 1}, 404),
    ],
)
def test_invalid_actions_are_refused_and_write_nothing(api, path, body, status):
    path = path.format(speaker=api.row(FIRST_PERSON)["id"], near=api.row(NEAR)["id"])
    assert api.post(path, body)[0] == status
    assert api.review()["count"] == 3
    assert api.sql("SELECT COUNT(*) FROM record_events") == [(0,)]
