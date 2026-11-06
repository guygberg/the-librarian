import json
import shutil
import sqlite3

import pytest
from support.cli import run_librarian
from support.recordings import make_env, run_import, search, transcriber_calls

from librarian.importer import recordings

ATLAS = "Atlas sync - 2026-10-12 10.00 GMT+03.00 - Recording"


def test_segments_are_stored_with_timestamps_and_searchable(tmp_path, home):
    env, _ = make_env(tmp_path, home, "base")
    code, _ = run_import(home, env)
    assert code == 0
    [hit] = search(home, "schema decisions")
    assert hit["source"] == "drive"
    item = json.loads(run_librarian(["show", hit["locator"]], home).stdout)
    content = json.loads(item["revisions"][0]["content"])
    assert (content["start"], content["end"], content["segment"]) == (0.0, 4.5, 1)
    assert item["origin_name"] == f"My Drive/Google Meet/Atlas sync - 2026-10-12 10.00 GMT+03.00/{ATLAS}"
    assert search(home, "תודה")  # flat folder layout, Hebrew title


def test_partial_file_is_not_yet_local_and_not_transcribed(tmp_path, home):
    env, _ = make_env(tmp_path, home, "recording_partial")
    code, out = run_import(home, env)
    assert code == 1 and "1 failed" in out
    assert search(home, "quokka") == []
    assert search(home, "walrus")
    [called] = transcriber_calls(home)
    assert "Retro" in called
    conn = sqlite3.connect(next(home.rglob("*.db")))
    [(error,)] = conn.execute("SELECT error FROM import_item_stages WHERE status = 'failed'").fetchall()
    assert "not yet local" in error and "Planning" in error


def test_transcribed_once_per_hash(tmp_path, home):
    env, fixtures = make_env(tmp_path, home, "base")
    run_import(home, env)
    first = len(transcriber_calls(home))
    assert first == 3
    run_import(home, env)
    copy = fixtures / "Meet Recordings" / "Copy - 2026-10-18 09.00 GMT+03.00 - Recording"
    shutil.copy(fixtures / "Meet Recordings" / "Standup - 2026-10-15 09.00 GMT+03.00 - Recording", copy)
    shutil.copy(copy.parent / "Standup - 2026-10-15 09.00 GMT+03.00 - Recording.transcript.json",
                copy.parent / (copy.name + ".transcript.json"))
    assert run_import(home, env)[0] == 0
    assert len(transcriber_calls(home)) == first


def test_failed_transcription_leaves_other_sources_searchable(tmp_path, home):
    env, fixtures = make_env(tmp_path, home, "base")
    for sidecar in fixtures.rglob("*.transcript.json"):
        sidecar.unlink()
    code, out = run_import(home, env)
    assert code == 1 and "3 failed" in out
    assert search(home, "importer")
    assert search(home, "גינה")
    assert search(home, "standup") == []


def test_parse_name_and_rejects_other_names():
    assert recordings.parse_name(ATLAS) == {"title": "Atlas sync", "date": "2026-10-12", "time": "10.00 GMT+03.00"}
    with pytest.raises(ValueError):
        recordings.parse_name("notes.txt")
