import hashlib
import sqlite3
import threading

import pytest
from support.cli import run_librarian

from librarian import db


@pytest.fixture
def lib_home(home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    return home


def write_migrations(directory, count):
    directory.mkdir(exist_ok=True)
    for n in range(1, count + 1):
        (directory / f"{n:04d}_m{n}.sql").write_text(f"CREATE TABLE t{n} (x);")
    return directory


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_migrate_creates_db_idempotently_and_status_is_read_only(home):
    out = run_librarian(["migrate", "--status"], home)
    assert out.stdout.strip() == "version 0, 1 pending"
    assert not (home / "workspaces" / "work" / "librarian.db").exists()

    first = run_librarian(["migrate"], home)
    again = run_librarian(["migrate"], home)
    assert first.returncode == again.returncode == 0
    assert first.stdout.strip() == again.stdout.strip() == "version 1"
    assert run_librarian(["migrate", "--status"], home).stdout.strip() == "version 1, 0 pending"
    assert not list((home / "workspaces" / "work").glob("backups/*"))


def test_core_tables_exist(lib_home):
    conn = db.connect_rw("work")
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "source_items", "source_item_revisions", "records", "links", "evidence",
        "persons", "aliases", "person_events",
    } <= tables  # fmt: skip
    for table in tables:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        assert "workspace" in cols, table


def test_old_schema_is_backed_up_then_migrated_keeping_last_three(lib_home, tmp_path):
    migrations = write_migrations(tmp_path / "m", 5)
    for step in range(1, 5):
        db.connect_rw("work", migrations_dir_upto(tmp_path, step)).close()
    backups = sorted((db.db_path("work").parent / "backups").glob("*.db"))
    assert len(backups) == 3
    assert db.current_version(db.db_path("work")) == 4

    db.connect_rw("work", migrations).close()
    assert db.current_version(db.db_path("work")) == 5
    newest = sorted((db.db_path("work").parent / "backups").glob("*.db"), key=lambda p: p.name)[-1]
    assert db.current_version(newest) == 4


def migrations_dir_upto(tmp_path, n):
    return write_migrations(tmp_path / f"upto{n}", n)


def test_cli_migrates_old_db_with_backup(home):
    path = home / "workspaces" / "work" / "librarian.db"
    path.parent.mkdir(parents=True)
    legacy = sqlite3.connect(path)
    legacy.execute("CREATE TABLE legacy (x)")
    legacy.commit()
    legacy.close()
    assert run_librarian(["migrate"], home).returncode == 0
    assert len(list(path.parent.glob("backups/*.db"))) == 1


def test_read_only_helper_cannot_write(lib_home):
    db.connect_rw("work").close()
    conn = db.connect_ro("work")
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO persons (workspace, name, created_at) VALUES ('work','a','t')")


def test_read_only_helper_raises_schema_outdated_without_touching_file(lib_home, tmp_path):
    old = write_migrations(tmp_path / "m", 1)
    db.connect_rw("work", old).close()
    path = db.db_path("work")
    before = digest(path)
    with pytest.raises(db.SchemaOutdated):
        db.connect_ro("work", write_migrations(tmp_path / "m2", 2))
    assert digest(path) == before


def test_missing_db_is_schema_outdated(lib_home):
    with pytest.raises(db.SchemaOutdated):
        db.connect_ro("work")
    assert not db.db_path("work").exists()


def test_wal_reader_reads_while_writer_holds_transaction(lib_home):
    writer = db.connect_rw("work")
    assert writer.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    writer.execute("BEGIN")
    writer.execute("INSERT INTO persons (workspace, name, created_at) VALUES ('work','a','t')")
    result = []
    t = threading.Thread(
        target=lambda: result.append(
            db.connect_ro("work").execute("SELECT count(*) FROM persons").fetchone()[0]
        )
    )
    t.start()
    t.join(5)
    writer.execute("COMMIT")
    assert result == [0]


def test_workspaces_use_separate_files(lib_home):
    db.connect_rw("work").close()
    db.connect_rw("other").close()
    assert db.db_path("work") != db.db_path("other")
    assert db.db_path("other").exists()
    conn = db.connect_rw("other")
    conn.execute("INSERT INTO persons (workspace, name, created_at) VALUES ('other','a','t')")
    assert db.connect_ro("work").execute("SELECT count(*) FROM persons").fetchone()[0] == 0


def test_person_events_are_append_only(lib_home):
    conn = db.connect_rw("work")
    conn.execute("INSERT INTO persons (workspace, name, created_at) VALUES ('work','a','t')")
    conn.execute(
        "INSERT INTO person_events (workspace, person_id, event, at) VALUES ('work',1,'merge','t')"
    )
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM person_events")
