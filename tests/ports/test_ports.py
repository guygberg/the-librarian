import json
import socket

import pytest

from librarian import engines
from librarian.fakes.extractor import ExtractionError
from librarian.transcribe.whisper_cpp import WhisperCppTranscriber


@pytest.fixture
def env(home, fixtures_dir, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    monkeypatch.setenv("LIBRARIAN_FIXTURES", str(fixtures_dir))
    monkeypatch.setenv("LIBRARIAN_ENGINES", "fake")
    return fixtures_dir


def test_fake_slack_pages_across_cursors_and_logs_only_reads(env):
    slack = engines.get_engines().slack
    assert slack.auth_info()["url"]
    channels = {c["id"] for c in slack.list_conversations()}
    assert "C001" in channels

    messages, cursor = [], None
    while True:
        page = slack.history("C001", cursor)
        messages += page["messages"]
        cursor = page["response_metadata"]["next_cursor"]
        if not cursor:
            break
    assert len(messages) > 200

    thread_ts = next(p.stem for p in (env / "slack" / "replies" / "C001").glob("*.json"))
    assert slack.replies("C001", thread_ts)

    methods = {c["method"] for c in engines.call_log("work").read()}
    assert methods == {"auth_info", "list_conversations", "history", "replies"}


def test_fake_slack_rejects_write_shaped_calls(env):
    with pytest.raises(AssertionError, match="write-shaped"):
        engines.get_engines().slack.post_message("C001", "hi")


def test_fake_transcriber_returns_sidecar_segments(env):
    recording = next(env.rglob("*Recording"))
    segments = engines.get_engines().transcriber.transcribe(recording, "m", "en")
    expected = json.loads((recording.parent / f"{recording.name}.transcript.json").read_text())["segments"]
    assert [s.text for s in segments] == [s["text"] for s in expected]
    assert segments[0].tokens[0].p == expected[0]["tokens"][0]["p"]


def test_fake_transcriber_missing_sidecar_is_clear(env, tmp_path):
    lonely = tmp_path / "lonely"
    lonely.write_bytes(b"x")
    with pytest.raises(FileNotFoundError, match="no sidecar transcript"):
        engines.get_engines().transcriber.transcribe(lonely, "m", "en")


def test_fake_extractor_canned_bad_and_failing_outputs(env):
    folder = env / "extraction"
    folder.mkdir()
    (folder / "good.json").write_text(json.dumps({"result": {"records": [{"id": 1}]}}))
    (folder / "badjson.json").write_text(json.dumps({"raw": "{not json"}))
    (folder / "boom.json").write_text(json.dumps({"error": "model crashed"}))
    extractor = engines.get_engines().extractor

    assert json.loads(extractor.extract("good", "text", [])) == {"records": [{"id": 1}]}
    assert extractor.extract("badjson", "text", []) == "{not json"
    with pytest.raises(ExtractionError, match="model crashed"):
        extractor.extract("boom", "text", [])
    with pytest.raises(ExtractionError, match="no canned output"):
        extractor.extract("missing", "text", [])
    assert [c["args"]["unit_key"] for c in engines.call_log("work").read()] == ["good", "badjson", "boom", "missing"]


def test_real_engines_are_placeholders(env, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_ENGINES", "real")
    real = engines.get_engines()
    assert isinstance(real.transcriber, WhisperCppTranscriber)
    with pytest.raises(NotImplementedError, match="not implemented yet"):
        real.extractor.extract("k", "t", [])


def test_unknown_engine_mode_is_rejected(env, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_ENGINES", "bogus")
    with pytest.raises(ValueError, match="fake"):
        engines.get_engines()


def test_fakes_never_touch_the_network(env, monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("network used")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    slack = engines.get_engines().slack
    assert slack.list_conversations()
    assert slack.history("C002")["messages"]
