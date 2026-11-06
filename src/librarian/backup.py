"""One dated archive of a Workspace: a consistent database snapshot, the Slack list and the config.

Session copies live in the database, so the snapshot carries them. Models and recordings are not
included.
"""

import io
import json
import shutil
import sqlite3
import tarfile
import tempfile
import time
from pathlib import Path

from librarian import db, paths

MANIFEST = "manifest.json"
DB_NAME = "librarian.db"
SLACK_LIST = "channels.json"
CONFIG = "config.toml"


class BackupError(Exception):
    pass


def archive_name(workspace: str) -> str:
    return f"librarian-{workspace}-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"


def _snapshot(source: Path, target: Path) -> int:
    """Copy via SQLite's backup API (safe while a writer holds the WAL).

    Returns the schema version.
    """
    src = db._open_ro(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        return db._version(dst)
    finally:
        dst.close()
        src.close()


def create(workspace: str, folder: Path) -> Path:
    source = db.db_path(workspace)
    if not source.exists():
        raise BackupError(f"no database for Workspace {workspace!r}; nothing to back up")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / archive_name(workspace)
    if target.exists():
        raise BackupError(f"{target} already exists")
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / DB_NAME
        migration = _snapshot(source, snapshot)
        manifest = json.dumps({"workspace": workspace, "migration": migration}).encode()
        partial = target.with_name(target.name + ".part")
        with tarfile.open(partial, "w:gz") as tar:
            tar.add(snapshot, DB_NAME)
            info = tarfile.TarInfo(MANIFEST)
            info.size = len(manifest)
            info.mtime = time.time()
            tar.addfile(info, io.BytesIO(manifest))
            for name, path in (
                (SLACK_LIST, paths.workspace_dir(workspace) / SLACK_LIST),
                (CONFIG, paths.config_path()),
            ):
                if path.exists():
                    tar.add(path, name)
        partial.rename(target)
    return target


def _members(tar: tarfile.TarFile) -> dict[str, tarfile.TarInfo]:
    members = {m.name: m for m in tar.getmembers()}
    allowed = {MANIFEST, DB_NAME, SLACK_LIST, CONFIG}
    if not {MANIFEST, DB_NAME} <= members.keys() or not members.keys() <= allowed:
        raise BackupError("not a Librarian backup archive")
    if not all(m.isreg() for m in members.values()):
        raise BackupError("not a Librarian backup archive")
    return members


def read_manifest(archive: Path) -> dict:
    try:
        with tarfile.open(archive) as tar:
            return json.loads(tar.extractfile(_members(tar)[MANIFEST]).read())
    except (tarfile.TarError, OSError, ValueError) as err:
        raise BackupError(f"cannot read {archive}: {err}") from err


def check_restorable(archive: Path) -> dict:
    manifest = read_manifest(archive)
    latest = db.latest_version()
    if manifest["migration"] > latest:
        raise BackupError(
            f"archive is at migration {manifest['migration']}, "
            f"this code only knows {latest}; update Librarian first"
        )
    return manifest


def is_empty(workspace: str) -> bool:
    """A Workspace folder with nothing but the lock file, and no config in the data folder."""
    folder = paths.workspace_dir(workspace)
    leftovers = [p for p in folder.iterdir() if p.name != "import.lock"] if folder.exists() else []
    return not leftovers and not paths.config_path().exists()


def restore(workspace: str, archive: Path) -> None:
    """Replace the Workspace's files with the archive's.

    The caller holds the lock and has checked emptiness.
    """
    check_restorable(archive)
    folder = paths.workspace_dir(workspace)
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder) as tmp, tarfile.open(archive) as tar:
        staged = Path(tmp)
        members = _members(tar)
        for name in members.keys() - {MANIFEST}:
            (staged / name).write_bytes(tar.extractfile(members[name]).read())
        for stale in (DB_NAME, f"{DB_NAME}-wal", f"{DB_NAME}-shm"):
            (folder / stale).unlink(missing_ok=True)
        shutil.move(staged / DB_NAME, folder / DB_NAME)
        if (staged / SLACK_LIST).exists():
            shutil.move(staged / SLACK_LIST, folder / SLACK_LIST)
        if (staged / CONFIG).exists():
            paths.config_path().parent.mkdir(parents=True, exist_ok=True)
            shutil.move(staged / CONFIG, paths.config_path())
    db.connect_rw(workspace).close()
