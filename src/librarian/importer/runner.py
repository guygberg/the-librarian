import sqlite3
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from librarian.importer import progress
from librarian.importer.stages import Deferred, Stage


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class Run:
    conn: sqlite3.Connection
    workspace: str
    id: int


def start_run(conn: sqlite3.Connection, workspace: str, pid: int) -> Run:
    """Caller holds the workspace lock, so any run still 'running' died without finishing."""
    conn.execute("UPDATE import_runs SET status = 'interrupted' WHERE status = 'running'")
    run_id = conn.execute(
        "INSERT INTO import_runs (workspace, pid, started_at, status) VALUES (?, ?, ?, 'running')",
        (workspace, pid, _now()),
    ).lastrowid
    return Run(conn, workspace, run_id)


def run_import(run: Run, stages: Sequence[Stage], report: Callable[[str], None]) -> int:
    """Run every stage in order; return how many items failed. Finished (item, stage) pairs are
    skipped."""
    conn = run.conn
    for index, stage in enumerate(stages):
        for source, item in stage.discover(conn):
            conn.execute(
                "INSERT OR IGNORE INTO import_items VALUES (?, ?, ?)", (run.workspace, source, item)
            )
        for source, item in _pending(run, [s.name for s in stages[: index + 1]]):
            _attempt(run, stage, source, item)
            report(progress.format_progress(conn, run.id))
    conn.execute(
        "UPDATE import_runs SET status = 'finished', ended_at = ? WHERE id = ?", (_now(), run.id)
    )
    return conn.execute(
        "SELECT COALESCE(SUM(n), 0) FROM import_counters WHERE run_id = ? AND counter = 'failed'",
        (run.id,),
    ).fetchone()[0]


def _pending(run: Run, names: list[str]) -> list[tuple[str, str]]:
    """Items done in every earlier stage and not yet done in the last of `names`."""
    *earlier, current = names
    done = {
        name: set(
            run.conn.execute(
                "SELECT source, item FROM import_item_stages "
                "WHERE workspace = ? AND stage = ? AND status = 'done'",
                (run.workspace, name),
            )
        )
        for name in names
    }
    items = run.conn.execute(
        "SELECT source, item FROM import_items WHERE workspace = ? ORDER BY source, item",
        (run.workspace,),
    ).fetchall()
    return [i for i in items if i not in done[current] and all(i in done[n] for n in earlier)]


def _attempt(run: Run, stage: Stage, source: str, item: str) -> None:
    try:
        stage.process(run.conn, source, item)
    except Deferred:
        return
    except Exception as exc:
        _record(run, stage, source, item, "failed", f"{type(exc).__name__}: {exc}")
        progress.bump(run, source, "failed")
        return
    _record(run, stage, source, item, "done", None)
    if stage.counter:
        progress.bump(run, source, stage.counter)


def _record(run: Run, stage: Stage, source: str, item: str, status: str, error: str | None) -> None:
    run.conn.execute(
        "INSERT OR REPLACE INTO import_item_stages VALUES (?, ?, ?, ?, ?, ?, ?)",
        (run.workspace, source, item, stage.name, status, error, run.id),
    )
