import os
import pty
import subprocess
import sys


def run_librarian(args, home, stdin=subprocess.DEVNULL):
    env = {**os.environ, "LIBRARIAN_HOME": str(home)}
    return subprocess.run(
        [sys.executable, "-m", "librarian", *args],
        env=env,
        stdin=stdin,
        capture_output=True,
        text=True,
    )


def run_python_under_pty(code: str) -> int:
    """Run `python -c code` with a pty as stdin; return its exit code."""
    master, slave = pty.openpty()
    try:
        proc = subprocess.run([sys.executable, "-c", code], stdin=slave, capture_output=True)
    finally:
        os.close(master)
        os.close(slave)
    return proc.returncode
