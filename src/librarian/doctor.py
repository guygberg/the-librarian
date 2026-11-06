"""`librarian doctor`: read-only checks of everything the real engines need.

Each failure comes with its fix.

Nothing is downloaded. The only network use is the one Slack read call, made through the Slack port.
"""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from librarian import engines, paths
from librarian.gate import training_gate_status

MIN_PYTHON = (3, 11)
MIN_WHISPER_CPP = (1, 7, 5)  # first release with `--vad`
DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / "models.manifest.json"
_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""
    fix: str = ""


def _fail(name: str, detail: str, fix: str) -> Check:
    return Check(name, False, detail, fix)


def _run(cmd: list[str]) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None


def _python() -> Check:
    if sys.version_info >= MIN_PYTHON:
        return Check("python", True)
    return _fail(
        "python",
        f"Python {sys.version_info[0]}.{sys.version_info[1]}",
        f"install Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer",
    )


def _ffmpeg(cfg: dict[str, Any]) -> Check:
    name = cfg.get("ffmpeg", "ffmpeg")
    if shutil.which(name):
        return Check("ffmpeg", True)
    return _fail("ffmpeg", f"`{name}` not found on PATH", "run `brew install ffmpeg`")


def _whisper(cfg: dict[str, Any]) -> list[Check]:
    name = cfg.get("whisper_cli", "whisper-cli")
    binary = shutil.which(name)
    if not binary:
        return [
            _fail("whisper.cpp", f"`{name}` not found on PATH", "run `brew install whisper-cpp`")
        ]
    minimum = ".".join(map(str, MIN_WHISPER_CPP))
    upgrade = f"run `brew upgrade whisper-cpp` (version {minimum} or newer is needed for --vad)"
    checks = []
    version = _run([binary, "--version"])
    found = _VERSION.search(version.stdout + version.stderr) if version else None
    if found and tuple(map(int, found.groups())) < MIN_WHISPER_CPP:
        checks.append(
            _fail("whisper.cpp version", f"{found.group(0)} is older than {minimum}", upgrade)
        )
    else:
        checks.append(Check("whisper.cpp version", True, "" if found else "version not reported"))
    helped = _run([binary, "--help"])
    if helped and "--vad" in helped.stdout + helped.stderr:
        checks.append(Check("whisper.cpp --vad", True))
    else:
        checks.append(_fail("whisper.cpp --vad", "this whisper.cpp does not accept --vad", upgrade))
    return checks


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _models(cfg: dict[str, Any]) -> list[Check]:
    manifest = Path(cfg.get("models_manifest_path") or DEFAULT_MANIFEST)
    checks = []
    for entry in json.loads(manifest.read_text(encoding="utf-8"))["models"]:
        path = Path(cfg.get(entry["config_key"]) or paths.data_home() / "models" / entry["name"])
        label = f"model {entry['name']}"
        if not path.is_file():
            checks.append(
                _fail(
                    label,
                    f"{entry['what']} not at {path}",
                    f"copy it there by hand (never downloaded for you) from {entry['url']}",
                )
            )
        elif not entry["sha256"]:
            checks.append(
                _fail(
                    label,
                    "hash not recorded",
                    f"hash not recorded: run shasum -a 256 {path} and record it in {manifest.name}",
                )
            )
        elif _sha256(path) != entry["sha256"]:
            checks.append(
                _fail(
                    label,
                    f"{path} does not match the manifest SHA-256",
                    f"copy the model again from {entry['url']}",
                )
            )
        else:
            checks.append(Check(label, True))
    return checks


def _claude(cfg: dict[str, Any]) -> Check:
    name = cfg.get("claude_bin", "claude")
    binary = shutil.which(name)
    if not binary:
        return _fail(
            "claude login",
            f"`{name}` not found on PATH",
            "install Claude Code and run `claude` to log in",
        )
    done = _run([binary, "auth", "status"])
    if done and done.returncode == 0:
        return Check("claude login", True)
    return _fail("claude login", "not logged in", f"run `{name}` and log in with your work account")


def _gate(cfg: dict[str, Any]) -> Check:
    status = training_gate_status(cfg)
    return (
        Check("no-training gate", True)
        if status.allowed
        else _fail("no-training gate", status.reason, status.fix)
    )


def _slack(cfg: dict[str, Any]) -> list[Check]:
    vendor = Path(cfg.get("slack_vendor_dir") or paths.data_home() / "vendor" / "slack")
    if not vendor.is_dir():
        return [
            _fail(
                "slack skill folder",
                f"{vendor} does not exist",
                "copy the Slack skill folder there by hand",
            )
        ]
    checks = [Check("slack skill folder", True)]
    try:
        engines.get_engines().slack.auth_info()
    except Exception as err:  # any failure of the read call is the finding
        checks.append(
            _fail(
                "slack login",
                f"read call failed: {err}",
                "log in with the Slack skill and set `slack_login_path` in the config",
            )
        )
    else:
        checks.append(Check("slack login", True))
    return checks


def _data_folder() -> Check:
    home = paths.data_home()
    if home.is_dir():
        return Check("data folder", True)
    return _fail("data folder", f"{home} does not exist", "run `librarian setup`")


def run_checks(cfg: dict[str, Any]) -> list[Check]:
    return [
        _python(),
        _ffmpeg(cfg),
        *_whisper(cfg),
        *_models(cfg),
        _claude(cfg),
        _gate(cfg),
        *_slack(cfg),
        _data_folder(),
    ]
