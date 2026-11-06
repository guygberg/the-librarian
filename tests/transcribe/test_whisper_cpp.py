import json
import os
import shutil
import socket
from pathlib import Path

import pytest
from support.cli import run_librarian
from support.recordings import make_env, run_import, search

from librarian import config, transcribe
from librarian.ports import Segment
from librarian.transcribe import language
from librarian.transcribe.whisper_cpp import EngineMissing, WhisperCppTranscriber

STUBS = Path(__file__).parent / "stubs"


@pytest.fixture
def rig(tmp_path, monkeypatch):
    """Stub `ffmpeg` and `whisper-cli` on PATH, model files in place, and the config that points at them."""
    bin_dir, models = tmp_path / "bin", tmp_path / "models"
    bin_dir.mkdir()
    models.mkdir()
    for name in ("ffmpeg", "whisper-cli"):
        shutil.copy(STUBS / name, bin_dir / name)
        (bin_dir / name).chmod(0o755)
    cfg = {}
    for key, name in (("hebrew_model_path", "he.bin"), ("english_model_path", "en.bin"), ("vad_model_path", "vad.bin")):
        (models / name).write_text("model")
        cfg[key] = str(models / name)
    log = tmp_path / "calls.log"
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "STUB_LOG": str(log),
        "STUB_WHISPER_JSON": str(STUBS / "whisper_output.json"),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    audio = tmp_path / "Standup - Recording"
    audio.write_text("mp4")

    def calls(tool):
        return [line.split("\t")[1:] for line in log.read_text().splitlines() if line.startswith(tool + "\t")] if log.exists() else []

    return cfg, env, audio, calls, models


def test_engine_runs_ffmpeg_then_whisper_with_model_language_and_vad(rig):
    cfg, _, audio, calls, models = rig
    segments = WhisperCppTranscriber(cfg).transcribe(audio, language.HEBREW_MODEL, "he")
    [ff] = calls("ffmpeg")
    assert ff[ff.index("-i") + 1] == str(audio)
    assert ff[ff.index("-ar") + 1] == "16000" and ff[ff.index("-ac") + 1] == "1"
    [wh] = calls("whisper-cli")
    assert wh[wh.index("-m") + 1] == str(models / "he.bin")
    assert wh[wh.index("-l") + 1] == "he"
    assert wh[wh.index("-vm") + 1] == str(models / "vad.bin") and "--vad" in wh
    assert wh[wh.index("-f") + 1] == ff[-1]  # whisper reads what ffmpeg wrote
    assert len(segments) == 2 and all(isinstance(s, Segment) for s in segments)


def test_english_model_file_for_english(rig):
    cfg, _, audio, calls, models = rig
    WhisperCppTranscriber(cfg).transcribe(audio, language.ENGLISH_MODEL, "en")
    [wh] = calls("whisper-cli")
    assert wh[wh.index("-m") + 1] == str(models / "en.bin") and wh[wh.index("-l") + 1] == "en"


def test_segments_carry_timestamps_metrics_and_real_tokens_only(rig):
    cfg, _, audio, _, _ = rig
    first, second = WhisperCppTranscriber(cfg).transcribe(audio, language.HEBREW_MODEL, "he")
    assert (first.start, first.end, first.text) == (0.0, 4.5, "we agreed on the schema decisions")
    assert [t.text for t in first.tokens] == [" we", " agreed", " schema"]  # [_BEG_] / [_TT_] markers dropped
    assert first.tokens[2].p == 0.2
    assert -1.0 < first.avg_logprob < 0 and first.no_speech_prob == 0.0 and first.compression_ratio > 0
    assert second.no_speech_prob == 0.7 and second.avg_logprob < -2.9  # ln(0.05): low-confidence input
    assert second.text == "תודה"


@pytest.mark.parametrize(("heard", "expected"), [("en", "en"), ("he", "he"), ("fr", "he")])
def test_detect_language_uses_first_thirty_seconds(rig, monkeypatch, heard, expected):
    cfg, _, audio, calls, _ = rig
    monkeypatch.setenv("STUB_DETECTED", heard)
    assert WhisperCppTranscriber(cfg).detect_language(audio) == expected
    [ff] = calls("ffmpeg")
    assert ff[ff.index("-t") + 1] == "30"
    assert "-dl" in calls("whisper-cli")[0]


@pytest.mark.parametrize(
    ("break_it", "named"),
    [
        (lambda cfg, bin_dir: (bin_dir / "ffmpeg").unlink(), "`ffmpeg`"),
        (lambda cfg, bin_dir: (bin_dir / "whisper-cli").unlink(), "`whisper-cli`"),
        (lambda cfg, bin_dir: Path(cfg["hebrew_model_path"]).unlink(), "Hebrew model"),
        (lambda cfg, bin_dir: Path(cfg["vad_model_path"]).unlink(), "voice-activity model"),
    ],
)
def test_missing_piece_is_a_clear_error_naming_doctor(rig, tmp_path, monkeypatch, break_it, named):
    cfg, env, audio, _, _ = rig
    bin_dir = tmp_path / "bin"
    break_it(cfg, bin_dir)
    monkeypatch.setenv("PATH", str(bin_dir))  # nothing else on PATH either
    with pytest.raises(EngineMissing) as err:
        WhisperCppTranscriber(cfg).transcribe(audio, language.HEBREW_MODEL, "he")
    assert named in str(err.value) and "librarian doctor" in str(err.value)


def test_no_network_use_and_no_download_helper(rig, monkeypatch):
    cfg, _, audio, _, _ = rig

    def refuse(*args, **kwargs):
        raise AssertionError("the transcriber touched the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    WhisperCppTranscriber(cfg).transcribe(audio, language.HEBREW_MODEL, "he")
    WhisperCppTranscriber(cfg).detect_language(audio)
    source = "".join(p.read_text() for p in Path(transcribe.__file__).parent.glob("*.py")).lower()
    for word in ("urllib", "requests", "http", "download", "socket"):
        assert word not in source


def test_real_engines_through_import_store_the_stubbed_transcript(rig, tmp_path):
    cfg, env, _, calls, _ = rig
    home = tmp_path / "home"
    fake_env, _ = make_env(tmp_path, home, "base", "".join(f'{k} = "{v}"\n' for k, v in cfg.items()))
    run_env = {**env, "LIBRARIAN_ENGINES": "real", "STUB_DETECTED": "en"}
    code, out = run_import(home, run_env)
    assert code == 0, out
    assert len(calls("whisper-cli")) == 6  # a detection and a transcription for each of the three recordings
    [hit] = search(home, "schema decisions")[:1]
    content = json.loads(json.loads(run_librarian(["show", hit["locator"]], home).stdout)["revisions"][0]["content"])
    assert (content["start"], content["end"], content["segment"]) == (0.0, 4.5, 1)
    assert search(home, "תודה")


@pytest.mark.skipif(os.environ.get("LIBRARIAN_MAC_SMOKE") != "1", reason="needs real whisper.cpp and ffmpeg")
def test_mac_smoke_real_engines_on_a_short_clip():
    clip = Path(os.environ["LIBRARIAN_SMOKE_CLIP"])
    engine = WhisperCppTranscriber(config.load())
    segments = engine.transcribe(clip, language.ENGLISH_MODEL, "en")
    assert segments and all(s.end >= s.start for s in segments)
