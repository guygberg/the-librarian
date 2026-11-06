import os
import sys
from pathlib import Path

from librarian.tty import require_terminal

help = (
    "Link the Claude Code skill into ~/.claude/skills "
    "and put a `librarian` shim in ~/.local/bin (terminal only)"
)

SKILL_SOURCE = Path(__file__).resolve().parents[3] / "skill"
SHIM_MARK = "# librarian shim"


def add_arguments(parser):
    pass


def _shim_text() -> str:
    return f'#!/bin/sh\n{SHIM_MARK}\nexec "{sys.executable}" -m librarian "$@"\n'


def _link_skill(target: Path) -> str:
    if target.is_symlink():
        if target.resolve() == SKILL_SOURCE:
            return "already linked"
        target.unlink()
    elif target.exists():
        raise SystemExit(f"librarian: {target} exists and is not a link; move it away first")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(SKILL_SOURCE, target_is_directory=True)
    return "linked"


def _write_shim(shim: Path) -> str:
    text = _shim_text()
    if shim.exists():
        current = shim.read_text()
        if current == text:
            return "already installed"
        if SHIM_MARK not in current:
            raise SystemExit(
                f"librarian: {shim} exists and is not the librarian shim; move it away first"
            )
    shim.parent.mkdir(parents=True, exist_ok=True)
    shim.write_text(text)
    shim.chmod(0o755)
    return "installed"


def run(args, ctx):
    require_terminal()
    home = Path.home()
    skill = home / ".claude" / "skills" / "librarian"
    shim = home / ".local" / "bin" / "librarian"
    print(f"skill {skill}: {_link_skill(skill)}")
    print(f"shim {shim}: {_write_shim(shim)}")
    if str(shim.parent) not in os.environ.get("PATH", "").split(os.pathsep):
        print(f"note: add {shim.parent} to your PATH so Claude can run `librarian`")
    return 0
