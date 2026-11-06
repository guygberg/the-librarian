import json
import re
import subprocess
import sys
from pathlib import Path

from fixtures.scenarios import payments_cutover as payments
from support.cli import finish_tty, popen_librarian_tty, run_librarian
from support.recordings import make_env

SRC = Path(__file__).resolve().parents[2] / "src" / "librarian"

BLOCK_NETWORK = """\
import socket

def _blocked(*args, **kwargs):
    raise OSError("network blocked by test")

socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked
"""


def blocked_env(tmp_path):
    folder = tmp_path / "block"
    folder.mkdir()
    (folder / "sitecustomize.py").write_text(BLOCK_NETWORK)
    return {"PYTHONPATH": str(folder)}


def test_the_network_block_really_blocks(tmp_path):
    code = "import socket; socket.create_connection(('127.0.0.1', 9))"
    env = blocked_env(tmp_path)
    proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert "network blocked by test" in proc.stderr


def test_fake_pipeline_runs_with_the_network_blocked(tmp_path, home):
    env, _ = make_env(tmp_path, home, "payments-cutover")
    env = {**env, **blocked_env(tmp_path), "LIBRARIAN_NOW": str(payments.NOW)}
    workspace = home / "workspaces" / "work"
    workspace.mkdir(parents=True)
    (workspace / "channels.json").write_text(json.dumps({"picked": ["C001"]}))
    code, out = finish_tty(popen_librarian_tty(["import"], home, env))
    assert code == 0, out
    for args in (["search", "Payments"], ["open-items"]):
        result = run_librarian(args, home, env=env)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "network blocked" not in result.stdout + result.stderr
    assert json.loads(run_librarian(["search", "Payments"], home, env=env).stdout)["evidence"]


def test_no_download_code_path_exists():
    sources = {path: path.read_text() for path in SRC.rglob("*.py")}
    downloaders = re.compile(r"urlretrieve|\bwget\b|\bcurl\b|\.download\(|hf_hub_download")
    assert [p.name for p, text in sources.items() if downloaders.search(text)] == []
    # The only network client is the Slack API reader; models are copied in by hand.
    assert {
        p.relative_to(SRC).as_posix() for p, text in sources.items() if "urllib.request" in text
    } == {"slack/client.py"}
