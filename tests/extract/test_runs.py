import json

import pytest

from extract.results import CANDIDATE_IDS, LOCATORS, UNIT_TEXT, dumps, good, with_record
from librarian import db, engines, paths
from librarian.extract import runs, schema
from support.cli import run_librarian


@pytest.fixture
def env(home, fixtures_dir, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    monkeypatch.setenv("LIBRARIAN_FIXTURES", str(fixtures_dir))
    monkeypatch.setenv("LIBRARIAN_ENGINES", "fake")
    folder = fixtures_dir / "extraction"
    folder.mkdir()
    (folder / "clean.json").write_text(json.dumps({"result": good()}))
    (folder / "dirty.json").write_text(json.dumps({"result": with_record(1, evidence=[])}))
    (folder / "garbage.json").write_text(json.dumps({"raw": "{not json"}))
    return home


def extract(conn, unit_key):
    return runs.extract_and_record(
        conn, "work", engines.get_engines().extractor, engines.get_engines().extractor.meta,
        unit_key, UNIT_TEXT, [{"id": i} for i in CANDIDATE_IDS], LOCATORS,
    )


def stored_runs(home):
    out = run_librarian(["runs", "--json"], home)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_run_record_holds_model_version_hashes_and_raw_envelope(env):
    conn = db.connect_rw("work")
    extract(conn, "clean")
    conn.close()

    (run,) = stored_runs(env)
    assert run["model"] == "fake-model"
    assert run["claude_code_version"] == "0.0.0-fake"
    assert len(run["prompt_hash"]) == 64
    assert run["prompt_hash"] != run["schema_hash"]
    assert run["schema_hash"] == schema.schema_hash()
    assert run["envelope"] == dumps(good())
    assert run["accepted_records"] == 4
    assert run["rejected"] == []


def test_runs_command_shows_rejection_counts_and_reasons(env):
    conn = db.connect_rw("work")
    extract(conn, "dirty")
    extract(conn, "garbage")
    conn.close()

    assert [(r["unit_key"], r["accepted_records"]) for r in stored_runs(env)] == [("dirty", 3), ("garbage", 0)]
    text = run_librarian(["runs"], env).stdout
    assert "dirty" in text and "rejected 1 (1 no_evidence)" in text
    assert "records[1]: no_evidence" in text
    assert "rejected 1 (1 invalid_json)" in text


def test_runs_command_on_a_missing_database_asks_for_migration(env):
    out = run_librarian(["runs"], env)
    assert out.returncode == 1
    assert "schema_outdated" in out.stdout
    assert not paths.workspace_dir("work").exists() or not db.db_path("work").exists()
