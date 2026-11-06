import json

import pytest
from fixtures.scenarios import people_aliases as p
from support.api import Api
from support.recordings import make_env, run_import
from support.serve import spawn

from librarian.importer import recordings

FIRST_PERSON = "By first person"
UNKNOWN = "unknown speaker"


@pytest.fixture
def api(tmp_path, home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    me_names = ", ".join(json.dumps(n, ensure_ascii=False) for n in p.ME_NAMES)
    env, fixtures = make_env(tmp_path, home, "people_aliases", f"me_names = [{me_names}]\n")
    env["LIBRARIAN_NOW"] = str(p.NOW)
    (home / "workspaces" / "work").mkdir(parents=True, exist_ok=True)
    (home / "workspaces" / "work" / "channels.json").write_text(json.dumps({"picked": ["C001"]}))
    code, out = run_import(home, env)
    assert code == 0, out
    proc, served = spawn(home, "--port", "0", env=env)
    api = Api(served, home, env)
    api.fixtures = fixtures
    yield api
    proc.terminate()
    proc.wait(timeout=10)
    proc.stdout.close()


def segment_locator(api):
    [(stable_id,)] = api.sql("SELECT stable_id FROM source_items WHERE source = 'drive'")
    return f"drive:{stable_id}"


def set_speaker(api, name="Dana Cohen"):
    return api.post("/api/speaker", {"locator": segment_locator(api), "person_id": api.person(name)})


def retranscribe(api, titles_and_matches):
    """The recording's bytes change (new file hash) and its segment comes back with shifted times; the canned
    extraction of the new segment holds one first-person Record per (title, match)."""
    recording = api.fixtures / "Meet Recordings" / p.RECORDING
    recording.write_bytes(recording.read_bytes() + b"re-encoded\n")
    sidecar = recording.with_name(recording.name + ".transcript.json")
    data = json.loads(sidecar.read_text())
    data["segments"][0]["start"] += 0.5
    data["segments"][0]["end"] += 0.5
    sidecar.write_text(json.dumps(data))
    conn = api.conn()
    with conn:  # Drive replaced the file: fetch it again
        conn.execute("DELETE FROM import_item_stages WHERE source = 'recording'")
    conn.close()
    prefix = recordings._file_hash(recording)[: recordings._ID_LENGTH]
    records = [
        {
            "ref": title, "match": match, "kind": "action_item", "title": title, "lifecycle": "open",
            "basis": "stated", "commitment": "request", "owner": {"speaker": "first_person"},
            "evidence": [{"locator": f"drive:{prefix}/1", "quote": p.FIRST_PERSON, "role": "supports"}],
        }
        for title, match in titles_and_matches
    ]
    (api.fixtures / "extraction" / f"drive-{prefix}-1.json").write_text(json.dumps({"result": {"records": records}}))


def test_setting_the_speaker_gives_the_record_an_owner_clears_its_review_entry_and_moves_the_open_item(api):
    assert api.show(FIRST_PERSON)["owner"] == UNKNOWN
    assert api.open_items()[FIRST_PERSON] != "other_open"

    status, out = set_speaker(api)
    assert status == 200 and [r["owner"] for r in out["records"]] == ["Dana Cohen"]

    shown = api.show(FIRST_PERSON)
    assert shown["owner"] == "Dana Cohen" and "suggested" not in shown
    assert [r for r in api.review()["rows"] if r["kind"] == "unknown_speaker"] == []
    assert api.open_items()[FIRST_PERSON] == "other_open"
    assert api.events("set_speaker") == ["set_speaker"]


def test_the_setting_survives_re_transcription_and_re_extraction(api):
    set_speaker(api)
    retranscribe(
        api,
        [(FIRST_PERSON, {"decision": "updated", "id": api.record(FIRST_PERSON)}), ("Resent report", {"decision": "new"})],
    )
    api.reimport()

    assert api.show(FIRST_PERSON)["owner"] == "Dana Cohen"
    assert api.show("Resent report")["owner"] == "Dana Cohen"
    assert [r for r in api.review()["rows"] if r["kind"] == "unknown_speaker"] == []


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"locator": "slack:C001/1", "person_id": 1}, 404),
        ({"locator": "drive:nothing/1", "person_id": 1}, 404),
        ({"locator": "garbage", "person_id": 1}, 400),
        ({"person_id": 1}, 400),
        ({"locator": "LOC", "person_id": 9999}, 404),
    ],
)
def test_invalid_settings_are_refused_and_write_nothing(api, body, status):
    body = {k: segment_locator(api) if v == "LOC" else v for k, v in body.items()}
    assert api.post("/api/speaker", body)[0] == status
    assert api.sql("SELECT COUNT(*) FROM segment_speakers") == [(0,)]
    assert api.row(FIRST_PERSON)["kind"] == "unknown_speaker"
