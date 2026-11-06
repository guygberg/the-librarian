import hashlib
import json
import socket

import pytest

from librarian import cli
from support.cli import run_librarian
from support.recordings import make_env

MODELS = {
    "ivrit-ggml-model.bin": b"hebrew",
    "ggml-large-v3-turbo.bin": b"english",
    "ggml-silero-vad.bin": b"vad",
}


def stub(path, body):
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


@pytest.fixture
def machine(tmp_path):
    """A fixture machine where every piece is present; tests break one piece."""
    home, bindir = tmp_path / "home", tmp_path / "bin"
    bindir.mkdir()
    env, fixtures = make_env(tmp_path, home, "people_aliases")
    stub(bindir / "ffmpeg", "exit 0")
    stub(bindir / "claude", "exit 0")
    stub(
        bindir / "whisper-cli",
        'case "$1" in --version) echo "whisper-cli 1.7.6";; *) echo "usage: --vad";; esac',
    )
    models = home / "models"
    models.mkdir()
    for name, content in MODELS.items():
        (models / name).write_bytes(content)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "name": n,
                        "what": n,
                        "config_key": k,
                        "url": f"https://example.invalid/{n}",
                        "sha256": hashlib.sha256(MODELS[n]).hexdigest(),
                    }
                    for n, k in (
                        ("ivrit-ggml-model.bin", "hebrew_model_path"),
                        ("ggml-large-v3-turbo.bin", "english_model_path"),
                        ("ggml-silero-vad.bin", "vad_model_path"),
                    )
                ]
            }
        )
    )
    vendor = home / "vendor" / "slack"
    vendor.mkdir(parents=True)
    with (home / "config.toml").open("a") as f:
        f.write(f'models_manifest_path = "{manifest}"\n')
    return {
        "home": home,
        "bin": bindir,
        "env": {**env, "PATH": str(bindir)},
        "vendor": vendor,
        "manifest": manifest,
        "fixtures": fixtures,
    }


def doctor(m):
    done = run_librarian(["doctor"], m["home"], env=m["env"])
    return done.returncode, done.stdout + done.stderr


def test_all_present_exits_zero(machine):
    code, out = doctor(machine)
    assert code == 0, out
    assert "FAIL" not in out


def test_missing_ffmpeg_is_named_with_its_fix(machine):
    (machine["bin"] / "ffmpeg").unlink()
    code, out = doctor(machine)
    assert code == 1
    assert "FAIL  ffmpeg" in out and "brew install ffmpeg" in out


def test_vad_model_hash_mismatch(machine):
    (machine["home"] / "models" / "ggml-silero-vad.bin").write_bytes(b"tampered")
    code, out = doctor(machine)
    assert code == 1
    assert "FAIL  model ggml-silero-vad.bin" in out and "does not match" in out


def test_missing_model_says_copy_by_hand(machine):
    (machine["home"] / "models" / "ivrit-ggml-model.bin").unlink()
    code, out = doctor(machine)
    assert code == 1
    assert "FAIL  model ivrit-ggml-model.bin" in out and "by hand" in out


def test_unrecorded_hash_fails_with_shasum_hint(machine):
    manifest = json.loads(machine["manifest"].read_text())
    manifest["models"][0]["sha256"] = ""
    machine["manifest"].write_text(json.dumps(manifest))
    code, out = doctor(machine)
    assert code == 1
    assert "hash not recorded: run shasum -a 256" in out


def test_missing_slack_vendor_folder(machine):
    machine["vendor"].rmdir()
    code, out = doctor(machine)
    assert code == 1
    assert "FAIL  slack skill folder" in out


def test_saved_login_read_call_failing(machine):
    (machine["fixtures"] / "slack" / "auth.test.json").unlink()
    code, out = doctor(machine)
    assert code == 1
    assert "FAIL  slack login" in out


def test_gate_unset(machine):
    config = machine["home"] / "config.toml"
    config.write_text(
        "".join(
            line
            for line in config.read_text().splitlines(keepends=True)
            if "account_type" not in line
        )
    )
    code, out = doctor(machine)
    assert code == 1
    assert "FAIL  no-training gate" in out and "librarian setup" in out


def test_claude_not_logged_in(machine):
    stub(machine["bin"] / "claude", "exit 1")
    code, out = doctor(machine)
    assert code == 1
    assert "FAIL  claude login" in out


def test_whisper_too_old(machine):
    stub(
        machine["bin"] / "whisper-cli",
        'case "$1" in --version) echo "whisper-cli 1.7.0";; *) echo "usage: --vad";; esac',
    )
    code, out = doctor(machine)
    assert code == 1
    assert "FAIL  whisper.cpp version" in out and "1.7.0" in out


def test_whisper_rejecting_vad(machine):
    stub(
        machine["bin"] / "whisper-cli",
        'case "$1" in --version) echo "whisper-cli 1.7.6";; *) echo "usage";; esac',
    )
    code, out = doctor(machine)
    assert code == 1
    assert "FAIL  whisper.cpp --vad" in out


def test_makes_no_network_call(machine, monkeypatch, capsys):
    def refuse(*args, **kwargs):
        raise AssertionError("network call")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    for key, value in machine["env"].items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LIBRARIAN_HOME", str(machine["home"]))
    assert cli.main(["doctor"]) == 0, capsys.readouterr().out
