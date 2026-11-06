"""One writer per Workspace: an advisory flock the OS drops when the process dies, even on
kill -9."""

import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path


class LockHeld(Exception):
    def __init__(self, holder: str):
        super().__init__(holder)
        self.holder = holder


@contextmanager
def workspace_lock(workspace_dir: Path):
    workspace_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(workspace_dir / "import.lock", os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LockHeld(os.pread(fd, 200, 0).decode().strip()) from None
        os.ftruncate(fd, 0)
        os.pwrite(
            fd, f"pid {os.getpid()} started {time.strftime('%Y-%m-%d %H:%M:%S')}\n".encode(), 0
        )
        yield
    finally:
        os.close(fd)
