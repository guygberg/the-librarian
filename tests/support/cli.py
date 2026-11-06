import os
import pty
import subprocess
import sys


def run_librarian(args, home, stdin=subprocess.DEVNULL, env=None):
    return subprocess.run(
        [sys.executable, "-m", "librarian", *args],
        env={**os.environ, "LIBRARIAN_HOME": str(home), **(env or {})},
        stdin=stdin,
        capture_output=True,
        text=True,
    )


def popen_librarian_tty(args, home, env=None):
    """Start `librarian` with a pty as stdin; the caller owns the process."""
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [sys.executable, "-m", "librarian", *args],
        env={**os.environ, "LIBRARIAN_HOME": str(home), **(env or {})},
        stdin=slave,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    os.close(slave)
    proc.pty_master = master
    return proc


def finish_tty(proc, timeout=30):
    out, _ = proc.communicate(timeout=timeout)
    os.close(proc.pty_master)
    return proc.returncode, out


def run_python_under_pty(code: str) -> int:
    """Run `python -c code` with a pty as stdin; return its exit code."""
    master, slave = pty.openpty()
    try:
        proc = subprocess.run([sys.executable, "-c", code], stdin=slave, capture_output=True)
    finally:
        os.close(master)
        os.close(slave)
    return proc.returncode
