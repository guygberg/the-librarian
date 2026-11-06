import sqlite3

COUNTERS = ("fetched", "transcribed", "extracted", "failed")


def bump(run, source: str, counter: str) -> None:
    run.conn.execute(
        "INSERT INTO import_counters VALUES (?, ?, ?, ?, 1) "
        "ON CONFLICT (run_id, source, counter) DO UPDATE SET n = n + 1",
        (run.workspace, run.id, source, counter),
    )


def format_progress(conn: sqlite3.Connection, run_id: int) -> str:
    rows = conn.execute(
        "SELECT source, counter, n FROM import_counters WHERE run_id = ?", (run_id,)
    ).fetchall()
    per_source: dict[str, dict[str, int]] = {}
    for source, counter, n in rows:
        per_source.setdefault(source, {})[counter] = n
    return "\n".join(
        f"{source}: " + ", ".join(f"{c} {counts.get(c, 0)}" for c in COUNTERS)
        for source, counts in sorted(per_source.items())
    )


def running_progress(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT id FROM import_runs WHERE status = 'running' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return (format_progress(conn, row[0]) if row else "") or "no items processed yet"
