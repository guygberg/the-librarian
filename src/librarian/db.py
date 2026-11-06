"""One SQLite file per Workspace.

Only `connect_rw` may write or migrate; answer paths use `connect_ro`.
"""

import re
import sqlite3
import time
from pathlib import Path

from librarian import paths

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
KEEP_BACKUPS = 3


class SchemaOutdated(Exception):
    def __init__(self, current: int, latest: int):
        super().__init__(f"schema is at version {current}, code needs {latest}")
        self.current = current
        self.latest = latest


def db_path(workspace: str) -> Path:
    return paths.workspace_dir(workspace) / "librarian.db"


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[tuple[int, Path]]:
    found = []
    for path in directory.glob("*.sql"):
        match = re.match(r"(\d+)_", path.name)
        if match:
            found.append((int(match.group(1)), path))
    return sorted(found)


def latest_version(directory: Path = MIGRATIONS_DIR) -> int:
    files = migration_files(directory)
    return files[-1][0] if files else 0


def _version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def current_version(path: Path) -> int:
    """Schema version of the file, read-only; 0 when it does not exist."""
    if not path.exists():
        return 0
    conn = _open_ro(path)
    try:
        return _version(conn)
    finally:
        conn.close()


def _open_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def connect_ro(workspace: str, directory: Path = MIGRATIONS_DIR) -> sqlite3.Connection:
    path = db_path(workspace)
    latest = latest_version(directory)
    if not path.exists():
        raise SchemaOutdated(0, latest)
    conn = _open_ro(path)
    version = _version(conn)
    if version < latest:
        conn.close()
        raise SchemaOutdated(version, latest)
    return conn


def connect_rw(workspace: str, directory: Path = MIGRATIONS_DIR) -> sqlite3.Connection:
    """Create the Workspace's database if needed and apply pending migrations."""
    path = db_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = [(v, p) for v, p in migration_files(directory) if v > current_version(path)]
    if pending and path.exists():
        _backup(path)
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    # Autocommit means one commit per statement; FULL would fsync each. NORMAL in WAL cannot
    # corrupt the file, and a re-run of the import redoes anything a power cut dropped.
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    for version, sql_path in pending:
        conn.executescript(
            f"BEGIN;\n{sql_path.read_text()}\nPRAGMA user_version={version};\nCOMMIT;"
        )
    return conn


def _backup(path: Path) -> None:
    folder = path.parent / "backups"
    folder.mkdir(exist_ok=True)
    target = folder / f"{path.stem}-v{current_version(path)}-{time.time_ns()}.db"
    src = sqlite3.connect(path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    for old in sorted(folder.glob(f"{path.stem}-v*.db"), key=lambda p: p.name.rsplit("-", 1)[1])[
        :-KEEP_BACKUPS
    ]:
        old.unlink()
