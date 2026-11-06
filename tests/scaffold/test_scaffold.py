import shutil
import subprocess
import sys
from pathlib import Path

from support.cli import run_librarian, run_python_under_pty

ROOT = Path(__file__).resolve().parents[2]

GUARDED = (
    "from librarian.tty import require_terminal\n"
    "require_terminal()\n"
    "open({marker!r}, 'w').close()\n"
)


def test_help_lists_discovered_commands(home):
    result = run_librarian(["--help"], home)
    assert result.returncode == 0
    assert "where" in result.stdout


def test_workspace_and_home_resolve_paths(home, tmp_path):
    default = run_librarian(["where"], home).stdout.strip()
    other = run_librarian(["--workspace", "other", "where"], home).stdout.strip()
    assert default == str(home.resolve() / "workspaces" / "work")
    assert other == str(home.resolve() / "workspaces" / "other")
    moved = run_librarian(["where"], tmp_path / "elsewhere").stdout.strip()
    assert moved.startswith(str((tmp_path / "elsewhere").resolve()))


def test_require_terminal_refuses_without_tty(tmp_path):
    marker = tmp_path / "written"
    proc = subprocess.run(
        [sys.executable, "-c", GUARDED.format(marker=str(marker))],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "terminal" in proc.stderr
    assert not marker.exists()


def test_require_terminal_proceeds_under_pty(tmp_path):
    marker = tmp_path / "written"
    assert run_python_under_pty(GUARDED.format(marker=str(marker))) == 0
    assert marker.exists()


def test_data_folder_is_git_ignored(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copy(ROOT / ".gitignore", repo / ".gitignore")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "check-ignore", "data/"], cwd=repo, check=True)
