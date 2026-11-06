"""Recording intake from the synced Drive folder.

The fetch stage finds recordings and checks each is fully local; the transcribe stage calls the Transcriber once
per file hash and stores each segment as a Source item `drive:<hash prefix>/<segment number>`, so Slack and session
text stays searchable while transcription is pending or failing.

Drive's file provider leaves a not-yet-downloaded file with its full size but (almost) no allocated blocks, so the
size on disk is compared with the size.
"""

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from librarian import config, store
from librarian.importer.stages import Stage
from librarian.ports import Transcriber

SOURCE = "recording"
SEGMENT_SOURCE = "drive"
_NAME = re.compile(r"(?P<title>.+) - (?P<date>\d{4}-\d{2}-\d{2}) (?P<time>.+) - Recording")
_FOLDERS = (Path("My Drive") / "Google Meet", Path("Meet Recordings"))
_ID_LENGTH = 16


def drive_dir() -> Path | None:
    value = config.load().get("drive_dir")
    return Path(value).expanduser() if value else None


def parse_name(name: str) -> dict[str, str]:
    """Title, date and time from `<title> - <date> <time> - Recording`."""
    match = _NAME.fullmatch(name)
    if match is None:
        raise ValueError(f"not a recording name: {name!r}")
    return match.groupdict()


def find_recordings(root: Path) -> Iterator[Path]:
    for folder in _FOLDERS:
        base = root / folder
        for path in sorted(base.rglob("*")) if base.is_dir() else ():
            if path.is_file() and _NAME.fullmatch(path.name):
                yield path


def _is_local(path: Path) -> bool:
    stat = path.stat()
    return stat.st_blocks * 512 >= stat.st_size


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_stage(workspace: str) -> Stage:
    root = drive_dir()

    def discover(conn: sqlite3.Connection) -> Iterator[tuple[str, str]]:
        if root is not None:
            for path in find_recordings(root):
                yield SOURCE, path.relative_to(root).as_posix()

    def process(conn: sqlite3.Connection, source: str, item: str) -> None:
        path = root / item
        if not path.is_file():
            raise FileNotFoundError(f"recording {item} is gone from the Drive folder")
        if not _is_local(path):
            raise OSError(f"recording {item} is not yet local: Drive has not downloaded it; retried next Import")
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO recording_files VALUES (?, ?, ?)", (workspace, item, _file_hash(path))
            )

    return Stage("fetch", process, discover, "fetched")


def transcribe_stage(workspace: str, transcriber: Transcriber) -> Stage:
    root = drive_dir()

    def process(conn: sqlite3.Connection, source: str, item: str) -> None:
        if source != SOURCE:
            return
        file_hash = conn.execute(
            "SELECT file_hash FROM recording_files WHERE workspace = ? AND path = ?", (workspace, item)
        ).fetchone()[0]
        if conn.execute(
            "SELECT 1 FROM recording_transcripts WHERE workspace = ? AND file_hash = ?", (workspace, file_hash)
        ).fetchone():
            return
        segments = transcriber.transcribe(root / item)
        meta = parse_name(Path(item).name)
        for number, segment in enumerate(segments, start=1):
            content = {
                "segment": number,
                "path": item,
                "title": meta["title"],
                "date": meta["date"],
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
            }
            store.upsert(
                conn,
                workspace,
                SEGMENT_SOURCE,
                f"{file_hash[:_ID_LENGTH]}/{number}",
                json.dumps(content, ensure_ascii=False, sort_keys=True),
                origin_name=item,
                origin_kind="recording",
            )
        with conn:
            conn.execute("INSERT INTO recording_transcripts VALUES (?, ?)", (workspace, file_hash))

    return Stage("transcribe", process, counter="transcribed")
