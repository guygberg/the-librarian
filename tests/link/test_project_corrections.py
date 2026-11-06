import pytest
from fixtures.scenarios import projects_stable_ids as s
from support.api import Api
from support.recordings import make_env, run_import
from support.serve import spawn

ATLAS, ATLASES, HELIOS = "Atlas Migration", "Atlas Migrations", "Helios"


@pytest.fixture
def api(tmp_path, home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    env, _ = make_env(tmp_path, home, "projects_stable_ids")
    env["LIBRARIAN_NOW"] = str(s.NOW)
    (home / "workspaces" / "work").mkdir(parents=True, exist_ok=True)
    (home / "workspaces" / "work" / "channels.json").write_text('{"picked": ["C001"]}')
    code, out = run_import(home, env)
    assert code == 0, out
    proc, served = spawn(home, "--port", "0", env=env)
    yield Api(served, home, env)
    proc.terminate()
    proc.wait(timeout=10)
    proc.stdout.close()


def project(api, name):
    """(the project `librarian project` resolves `name` to, the titles of its Records)"""
    out = api.cli("project", name)
    resolved = out["resolved"]["project"]
    return resolved and resolved["name"], {r["title"] for r in out["records"]} - {resolved and resolved["name"]}


def inferred(api):
    return {r["record"]["title"] for r in api.review()["rows"] if r["kind"] == "inferred_project"}


def test_confirm_marks_the_project_stated_by_me_and_leaves_review(api):
    assert ATLAS in inferred(api)

    status, view = api.post(f"/api/projects/{api.record(ATLAS)}/confirm")

    assert (status, view["basis"]) == (200, "confirmed")
    assert ATLAS not in inferred(api) and ATLASES in inferred(api)
    assert api.sql("SELECT basis FROM records WHERE title = ?", ATLAS) == [("confirmed",)]


def test_rename_keeps_the_old_name_reaching_the_project(api):
    atlas = api.record(ATLAS)

    status, view = api.post(f"/api/projects/{atlas}/rename", {"name": "Atlas Cloud"})

    assert (status, view["title"]) == (200, "Atlas Cloud")
    assert project(api, "Atlas Cloud") == ("Atlas Cloud", {"Draft the plan"})
    assert project(api, ATLAS)[0] == "Atlas Cloud"  # the old title is an Alias now


def test_rename_to_another_projects_name_is_refused(api):
    status, body = api.post(f"/api/projects/{api.record(ATLAS)}/rename", {"name": "atlas  migrations"})

    assert status == 409 and "error" in body
    assert api.sql("SELECT title FROM records WHERE id = ?", api.record(ATLAS)) == [(ATLAS,)]


def test_merge_moves_records_and_names_and_settles_the_suggestion(api):
    atlas, atlases = api.record(ATLAS), api.record(ATLASES)
    kinds = {r["kind"] for r in api.review()["rows"] if r["record"]["id"] == atlases}
    assert kinds == {"inferred_project", "merge_project"}

    status, view = api.post(f"/api/projects/{atlases}/merge", {"into": atlas})

    assert (status, view["id"]) == (200, atlas)
    assert project(api, ATLAS) == (ATLAS, {"Draft the plan", "Write the notes"})
    assert project(api, ATLASES)[0] == ATLAS  # the old name is an Alias of the survivor
    assert api.show(ATLASES)["lifecycle"] == "superseded"
    assert not [r for r in api.review()["rows"] if atlases in (r["record"]["id"], (r.get("other") or {}).get("id"))]


def test_merge_persists_across_a_reimport_that_would_recreate_the_old_name(api):
    api.post(f"/api/projects/{api.record(ATLASES)}/merge", {"into": api.record(ATLAS)})

    api.reimport()

    assert api.sql("SELECT COUNT(*) FROM records WHERE kind = 'project' AND title IN (?, ?)", ATLAS, ATLASES) == [(2,)]
    assert api.show(ATLASES)["lifecycle"] == "superseded"
    assert project(api, ATLAS) == (ATLAS, {"Draft the plan", "Write the notes"})
    assert project(api, HELIOS)[1] == {"Book the venue"}  # an unrelated project is untouched


def test_the_importer_never_merges_by_itself(api):
    api.reimport()

    assert api.sql("SELECT COUNT(*) FROM records WHERE kind = 'project' AND lifecycle = 'superseded'") == [(0,)]
    assert api.events("merge") == []


def test_split_gives_chosen_records_to_a_new_project(api):
    atlas, plan = api.record(ATLAS), api.record("Draft the plan")

    status, view = api.post(f"/api/projects/{atlas}/split", {"name": "Atlas Planning", "record_ids": [plan]})

    assert (status, view["title"]) == (200, "Atlas Planning")
    assert project(api, "Atlas Planning") == ("Atlas Planning", {"Draft the plan"})
    assert project(api, ATLAS) == (ATLAS, set())


def test_a_moved_record_stays_moved_after_a_reimport(api):
    plan = api.record("Draft the plan")

    status, view = api.post(f"/api/records/{plan}/project", {"project_id": api.record(ATLASES)})

    assert (status, view["projects"]) == (200, [{"id": api.record(ATLASES), "title": ATLASES}])
    assert project(api, ATLASES)[1] == {"Draft the plan", "Write the notes"}
    assert project(api, ATLAS)[1] == set()
    api.reimport()
    assert project(api, ATLASES)[1] == {"Draft the plan", "Write the notes"}


@pytest.mark.parametrize(
    ("path", "body", "status"),
    [
        ("merge", {"into": "self"}, 400),
        ("merge", {"into": 99999}, 404),
        ("merge", {"into": "plan"}, 404),  # a Record is not a project
        ("merge", {}, 400),
        ("rename", {"name": "  "}, 400),
        ("rename", {}, 400),
        ("split", {"name": "New", "record_ids": []}, 400),
        ("split", {"name": "New", "record_ids": ["x"]}, 400),
        ("split", {"name": "New", "record_ids": "other"}, 404),  # a Record of another project
        ("split", {"name": ATLASES, "record_ids": "own"}, 409),
    ],
)
def test_invalid_operations_are_refused_and_write_nothing(api, path, body, status):
    atlas, plan, notes = api.record(ATLAS), api.record("Draft the plan"), api.record("Write the notes")
    names = {"self": atlas, "plan": plan, "other": [notes], "own": [plan]}
    body = {k: names.get(v, v) if isinstance(v, str) else v for k, v in body.items()}
    before = [api.sql(q) for q in ("SELECT * FROM records", "SELECT * FROM links", "SELECT * FROM record_events", "SELECT * FROM project_aliases")]

    got, answer = api.post(f"/api/projects/{atlas}/{path}", body)

    assert got == status and "error" in answer
    assert before == [api.sql(q) for q in ("SELECT * FROM records", "SELECT * FROM links", "SELECT * FROM record_events", "SELECT * FROM project_aliases")]


def test_an_unknown_project_is_a_404(api):
    assert api.post("/api/projects/99999/confirm")[0] == 404
    assert api.post(f"/api/projects/{api.record('Draft the plan')}/confirm")[0] == 404
