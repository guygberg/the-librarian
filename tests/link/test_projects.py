import json
import random
import sqlite3

import pytest
from fixtures import formats as f
from fixtures.build import build
from fixtures.scenarios import projects_stable_ids as s
from support.cli import finish_tty, popen_librarian_tty, run_librarian

from librarian import db, engines, store
from librarian.extract import stage as extract
from librarian.fakes.calllog import CallLog
from librarian.importer import recordings
from librarian.importer.stages import Deferred


@pytest.fixture
def world(tmp_path, home):
    fixtures = tmp_path / "fixtures"
    build(fixtures, "projects_stable_ids")
    home.mkdir(parents=True)
    (home / "config.toml").write_text(
        f'account_type = "team"\nusage_rules_confirmed = true\ndrive_dir = "{fixtures}"\n'
        f'claude_projects_dir = "{fixtures}/none"\n'
    )
    workspace = home / "workspaces" / "work"
    workspace.mkdir(parents=True)
    (workspace / "channels.json").write_text(json.dumps({"picked": ["C001"]}))
    env = {"LIBRARIAN_ENGINES": "fake", "LIBRARIAN_FIXTURES": str(fixtures), "LIBRARIAN_NOW": str(s.NOW)}
    return home, env, fixtures


def run_import(world):
    home, env, _ = world
    code, out = finish_tty(popen_librarian_tty(["import"], home, env))
    assert code == 0, out


def query(home, sql, *args):
    return sqlite3.connect(next(home.rglob("*.db"))).execute(sql, args).fetchall()


def show(home, record_id):
    out = run_librarian(["show", str(record_id)], home)
    assert out.returncode == 0, out.stdout
    return json.loads(out.stdout)


def extractor_calls(home, key):
    return [c["args"] for c in CallLog(home / "workspaces" / "work").read() if c["engine"] == "extractor" and c["args"]["unit_key"] == key]


def add_recording(world, name, text, *calls):
    """A recording of one segment, with the Records Claude finds in it on each call; returns its unit key."""
    _, _, fixtures = world
    flat = fixtures / "Meet Recordings"
    f.write_recording(flat, name, [f.segment(0.0, 3.0, text, random.Random(7))])
    file_id = recordings._file_hash(flat / name)[: recordings._ID_LENGTH]
    key = f"drive-{file_id}-1"
    located = [
        {"result": {"records": [{**r, "evidence": [{**e, "locator": f"drive:{file_id}/1"} for e in r["evidence"]]} for r in records]}}
        for records in calls
    ]
    (fixtures / "extraction" / f"{key}.json").write_text(json.dumps({"calls": located}))
    return key


def action(title, quote, links, **extra):
    return {
        "ref": title, "match": {"decision": "new"}, "kind": "action_item", "title": title, "lifecycle": "open",
        "basis": "stated", "commitment": "request", "links": links,
        "evidence": [{"locator": "", "quote": quote, "role": "supports"}], **extra,
    }


def project(title, quote):
    return {
        "ref": "p", "match": {"decision": "new"}, "kind": "project", "title": title, "lifecycle": "open", "basis": "stated",
        "evidence": [{"locator": "", "quote": quote, "role": "supports"}],
    }


def test_extraction_created_projects_are_inferred_and_wait_for_review(world):
    run_import(world)
    home = world[0]

    assert query(home, "SELECT id, basis FROM records WHERE kind = 'project' ORDER BY id") == [(1, "inferred"), (3, "inferred")]
    assert query(home, "SELECT record_id FROM review_entries WHERE kind = 'inferred_project' ORDER BY record_id") == [(1,), (3,)]
    assert {"kind": "inferred_project", "mark": "inferred project", "link": "project", "raw_name": "Atlas Migration"} in show(home, 1)["suggested"]


def test_reextraction_after_an_edit_keeps_the_record_ids(world):
    run_import(world)
    home = world[0]
    assert query(home, "SELECT id, title FROM records ORDER BY id") == [
        (1, "Atlas Migration"), (2, "Draft the plan"), (3, "Atlas Migrations"), (4, "Write the notes")]

    run_import(world)  # the second generation edits message 1 and adds message 3

    titles = dict(query(home, "SELECT id, title FROM records ORDER BY id"))
    assert [titles[i] for i in (1, 2, 3, 4)] == ["Atlas Migration", "Draft the plan", "Atlas Migrations", "Write the notes"]
    assert sorted(titles.values()).count("Atlas Migration") == 1 and len(titles) == 6
    assert show(home, 2)["stated_deadline"] == "2023-11-17"
    assert show(home, 2)["projects"] == [{"id": 1, "title": "Atlas Migration"}]
    sent = extractor_calls(home, s.KEYS[1])[1]["candidates"]
    assert {1, 2} <= set(sent)  # the project is named in the text, so its Records went with the call


def test_recording_about_an_existing_project_reuses_it_without_a_new_inferred_one(world):
    run_import(world)
    home = world[0]
    add_recording(world, "Sync - 2026-10-12 10.00 GMT+03.00 - Recording", "Atlas  migration review, Sam checks the budget", [
        project("atlas  MIGRATION", "Atlas  migration review"),
        action("Check the budget", "Sam checks the budget", [{"type": "belongs_to", "to": {"ref": "p"}}]),
    ])

    run_import(world)

    assert query(home, "SELECT COUNT(*) FROM records WHERE kind = 'project' AND title LIKE 'atlas%migration'") == [(1,)]
    (budget,) = query(home, "SELECT id FROM records WHERE title = 'Check the budget'")
    assert show(home, budget[0])["projects"] == [{"id": 1, "title": "Atlas Migration"}]
    assert query(home, "SELECT COUNT(*) FROM review_entries WHERE kind = 'inferred_project'") == [(3,)]  # Atlas Migration, Atlas Migrations, Helios


def test_project_alias_links_like_the_name(world):
    run_import(world)
    home = world[0]
    sqlite3.connect(next(home.rglob("*.db"))).execute("INSERT INTO project_aliases VALUES ('work', 1, 'Moving Atlas')").connection.commit()
    add_recording(world, "Sync - 2026-10-13 10.00 GMT+03.00 - Recording", "Moving Atlas: Sam books the room", [
        project("moving atlas", "Moving Atlas"),
        action("Book the room", "Sam books the room", [{"type": "belongs_to", "to": {"ref": "p"}}]),
    ])

    run_import(world)

    (room,) = query(home, "SELECT id FROM records WHERE title = 'Book the room'")
    assert show(home, room[0])["projects"] == [{"id": 1, "title": "Atlas Migration"}]


def test_near_name_is_only_suggested_and_nothing_is_merged(world):
    run_import(world)
    home = world[0]

    assert query(home, "SELECT COUNT(*) FROM records WHERE kind = 'project'") == [(2,)]
    assert show(home, 4)["projects"] == [{"id": 3, "title": "Atlas Migrations"}]
    assert {"kind": "suggested_project", "mark": "suggested project", "link": "belongs_to", "raw_name": "Atlas Migration"} in show(home, 4)["suggested"]
    assert query(home, "SELECT record_id, other_record_id FROM review_entries WHERE kind = 'merge_project'") == [(3, 1)]
    assert query(home, "SELECT COUNT(*) FROM links WHERE type = 'belongs_to' AND to_id = 1") == [(1,)]  # only its own action


def test_ambiguous_name_stays_unresolved(world):
    run_import(world)
    home = world[0]
    conn = sqlite3.connect(next(home.rglob("*.db")))
    conn.executemany("INSERT INTO project_aliases VALUES ('work', ?, 'Helios')", [(1,), (3,)])
    conn.commit()

    run_import(world)

    (helios,) = query(home, "SELECT id FROM records WHERE title = 'Helios'")
    kinds = query(home, "SELECT kind FROM review_entries WHERE record_id = ?", helios[0])
    assert kinds == [("inferred_project",)]
    (venue,) = query(home, "SELECT id FROM records WHERE title = 'Book the venue'")
    assert show(home, venue[0])["projects"] == [{"id": helios[0], "title": "Helios"}]
    assert query(home, "SELECT COUNT(*) FROM review_entries WHERE kind IN ('merge_project', 'suggested_project')") == [(2,)]  # the near pair only


def test_a_recording_that_never_names_its_project_is_rerun_once_with_that_projects_records(world):
    run_import(world)
    home = world[0]
    link = [{"type": "belongs_to", "to": {"id": 1}}]
    key = add_recording(
        world, "Sync - 2026-10-14 10.00 GMT+03.00 - Recording", "We should send the revised numbers",
        [action("Send the numbers", "send the revised numbers", link)],
        [action("Draft the plan", "send the revised numbers", link) | {"match": {"decision": "same", "id": 2}}],
    )

    run_import(world)

    calls = extractor_calls(home, key)
    assert len(calls) == 2
    assert 2 not in calls[0]["candidates"] and 1 in calls[0]["candidates"]  # the project list only
    assert {1, 2} <= set(calls[1]["candidates"])
    assert query(home, "SELECT COUNT(*) FROM records WHERE title IN ('Draft the plan', 'Send the numbers')") == [(1,)]
    assert any(e["locator"].startswith("drive:") for e in show(home, 2)["evidence"])


def test_the_rerun_counts_against_the_call_cap(tmp_path, home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    monkeypatch.setenv("LIBRARIAN_ENGINES", "fake")
    fixtures = tmp_path / "fixtures"
    (fixtures / "extraction").mkdir(parents=True)
    monkeypatch.setenv("LIBRARIAN_FIXTURES", str(fixtures))
    conn = db.connect_rw("work")
    conn.execute(
        "INSERT INTO records (id, workspace, kind, title, lifecycle, basis, created_at, updated_at)"
        " VALUES (1, 'work', 'project', 'Atlas', 'open', 'stated', 'x', 'x')"
    )
    store.upsert(conn, "work", "drive", "abc/1", json.dumps({"segment": 1, "start": 0.0, "text": "send the numbers"}), origin_name="talk.m4a")
    linked = action("Send numbers", "send the numbers", [{"type": "belongs_to", "to": {"id": 1}}])
    linked["evidence"][0]["locator"] = "drive:abc/1"
    (fixtures / "extraction" / "drive-abc-1.json").write_text(json.dumps({"calls": [{"result": {"records": [linked]}}]}))
    log = CallLog(db.db_path("work").parent)

    capped = extract.stage("work", engines.get_engines().extractor, max_calls=1)
    with pytest.raises(Deferred):
        capped.process(conn, "recording", "talk.m4a")
    assert len(log.read()) == 1  # no room for the re-run: the unit waits for the next run

    enough = extract.stage("work", engines.get_engines().extractor, max_calls=2)
    enough.process(conn, "recording", "talk.m4a")
    assert len(log.read()) == 3  # its first call again, plus the one re-run
    assert conn.execute("SELECT COUNT(*) FROM records WHERE title = 'Send numbers'").fetchone() == (1,)
