"""The Import the UI starts: a child `librarian import` process. The Workspace lock and the database are the
truth about it, so a second start (from here or the CLI) is refused and a killed Import leaves nothing behind.
"""

import os
import sqlite3
import subprocess
import sys
import threading
from datetime import UTC, datetime
from typing import Any

from librarian import paths
from librarian.importer.lock import LockHeld, workspace_lock
from librarian.importer.progress import COUNTERS
from librarian.query import envelope

_guard = threading.Lock()
_child: subprocess.Popen | None = None


def start(workspace: str, *args: str) -> bool:
    """Launch an Import; False when one already runs. `_child` covers the gap before the child takes the lock."""
    global _child
    with _guard:
        if _child is not None and _child.poll() is None:
            return False
        workspace_dir = paths.workspace_dir(workspace)
        try:
            with workspace_lock(workspace_dir):
                pass
        except LockHeld:
            return False
        with open(workspace_dir / "import-ui.log", "ab") as log:
            _child = subprocess.Popen(
                [sys.executable, "-m", "librarian", "--workspace", workspace, "import", "--from-serve", *args],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        return True


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def snapshot(conn: sqlite3.Connection, workspace: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Per-source counters of the latest Import, extraction calls it made, failed items, and Freshness."""
    row = conn.execute(
        "SELECT id, pid, started_at, ended_at, status FROM import_runs WHERE workspace = ? ORDER BY id DESC LIMIT 1",
        (workspace,),
    ).fetchone()
    # The child counts as running from its launch, before it has written its run row.
    run, running, sources, calls = None, _child is not None and _child.poll() is None, {}, 0
    if row:
        run = dict(zip(("id", "pid", "started_at", "ended_at", "status"), row))
        alive = run["status"] == "running" and _alive(run["pid"])
        running = running or alive
        if run["status"] == "running" and not alive:
            run["status"] = "interrupted"  # killed: the row was never closed, the lock is already gone
        for source, counter, n in conn.execute(
            "SELECT source, counter, n FROM import_counters WHERE run_id = ?", (run["id"],)
        ):
            sources.setdefault(source, dict.fromkeys(COUNTERS, 0))[counter] = n
        since = datetime.strptime(run["started_at"], "%Y-%m-%d %H:%M:%S").astimezone(UTC).isoformat()
        calls = conn.execute(
            "SELECT COUNT(*) FROM extraction_runs WHERE workspace = ? AND created_at >= ?", (workspace, since)
        ).fetchone()[0]
    failed = [
        {"source": s, "item": i, "stage": stage, "error": error}
        for s, i, stage, error in conn.execute(
            "SELECT source, item, stage, error FROM import_item_stages WHERE workspace = ? AND status = 'failed'"
            " ORDER BY source, item",
            (workspace,),
        )
    ]
    return {
        "running": running,
        "run": run,
        "sources": sources,
        "calls": calls,
        "failed": failed,
        "freshness": envelope.freshness(conn, workspace, cfg, datetime.now().astimezone()),
    }
