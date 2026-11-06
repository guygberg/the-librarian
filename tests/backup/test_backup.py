import io
import os
import sqlite3
import tarfile

import pytest
from support.cli import finish_tty, popen_librarian_tty, run_librarian
from support.recordings import make_env, run_import

from librarian import db
from librarian.importer.lock import workspace_lock


@pytest.fixture
def imported(tmp_path):
    home = tmp_path / "home"
    env, _ = make_env(tmp_path, home, "people_aliases")
    code, out = run_import(home, env)
    assert code == 0, out
    return home, env


def backup_of(home, folder):
    done = run_librarian(["backup", str(folder)], home)
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout.strip()


def restore_in_pty(home, archive, answers=(), *flags):
    proc = popen_librarian_tty(["restore", str(archive), *flags], home)
    os.write(proc.pty_master, "".join(a + "\n" for a in answers).encode())
    return finish_tty(proc)


def answers(home):
    return [run_librarian([*cmd], home).stdout for cmd in (["open-items"], ["project", "Atlas"])]


def tree(home):
    return sorted(str(p.relative_to(home)) for p in home.rglob("*") if p.name != "import.lock")


def test_round_trip_gives_identical_answers_and_archive_has_the_parts(imported, tmp_path):
    home, _ = imported
    archive = backup_of(home, tmp_path / "out")
    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
    assert {"librarian.db", "manifest.json", "config.toml"} <= names
    assert not any(n.startswith(("models", "recordings")) for n in names)

    fresh = tmp_path / "fresh"
    code, out = restore_in_pty(fresh, archive)
    assert code == 0, out
    assert answers(fresh) == answers(home)
    assert answers(fresh)[0].strip()


def test_restore_refuses_non_empty_folder_and_overwrite_needs_typed_confirmation(imported, tmp_path):
    home, _ = imported
    archive = backup_of(home, tmp_path / "out")
    before = tree(home)

    code, out = restore_in_pty(home, archive)
    assert code == 1 and "not empty" in out
    code, out = restore_in_pty(home, archive, ["nope"], "--overwrite")
    assert code == 1 and "nothing restored" in out
    assert tree(home) == before

    code, out = restore_in_pty(home, archive, ["work"], "--overwrite")
    assert code == 0, out


def test_restore_refuses_archive_with_newer_migration_and_changes_nothing(imported, tmp_path):
    home, _ = imported
    archive = backup_of(home, tmp_path / "out")
    newer = tmp_path / "newer.tar.gz"
    with tarfile.open(archive) as src, tarfile.open(newer, "w:gz") as dst:
        for member in src.getmembers():
            data = src.extractfile(member).read()
            if member.name == "manifest.json":
                data = data.replace(b'"migration": ', b'"migration": 9')
                member.size = len(data)
            dst.addfile(member, io.BytesIO(data))

    fresh = tmp_path / "fresh"
    code, out = restore_in_pty(fresh, newer)
    assert code == 1 and "update Librarian" in out
    assert not (fresh / "workspaces" / "work" / "librarian.db").exists()
    code, out = restore_in_pty(home, newer, ["work"], "--overwrite")
    assert code == 1


def test_backup_during_an_import_is_a_consistent_snapshot_and_restore_needs_terminal_and_lock(imported, tmp_path):
    home, _ = imported
    workspace_dir = home / "workspaces" / "work"
    archive = backup_of(home, tmp_path / "ok")

    writer = sqlite3.connect(workspace_dir / "librarian.db", isolation_level=None)
    try:
        with workspace_lock(workspace_dir):
            writer.execute("BEGIN")
            writer.execute("CREATE TABLE half_written (x)")
            during = backup_of(home, tmp_path / "during")
            writer.execute("ROLLBACK")

            before = tree(home)
            code, out = restore_in_pty(home, archive, ["work"], "--overwrite")
            assert code == 1 and "import is running" in out
            assert tree(home) == before
    finally:
        writer.close()
    with tarfile.open(during) as tar:
        tar.extract("librarian.db", tmp_path / "snap")
    snap = sqlite3.connect(tmp_path / "snap" / "librarian.db")
    assert snap.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert snap.execute("PRAGMA user_version").fetchone()[0] == db.latest_version()
    assert snap.execute("SELECT name FROM sqlite_master WHERE name='half_written'").fetchall() == []
    snap.close()

    plain = run_librarian(["restore", archive], tmp_path / "fresh2")
    assert plain.returncode != 0 and "needs a terminal" in plain.stderr
    assert not (tmp_path / "fresh2" / "workspaces").exists()
