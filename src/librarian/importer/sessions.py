"""Claude session fetch stage: each evidence line of a session `.jsonl` becomes a Source item in the store.

Claude Code deletes old sessions, so the filtered text is copied into the store. What is dropped before storing:
tool calls and results of `librarian` commands, and assistant text after the first `librarian` call of a
session, so the Librarian's own answers never come back as evidence. Item id is `<session id>/<line number>`;
the timestamp is part of the stored content.
"""

import json
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from librarian import config, paths, store
from librarian.importer.stages import Stage

SOURCE = "session"
_LIBRARIAN_COMMAND = re.compile(r"(?:^|[\s;&|(])librarian(?:\s|$)")
_OWN_WORKTREES = "--worktrees-"


def projects_dir() -> Path:
    return Path(config.load().get("claude_projects_dir", "~/.claude/projects")).expanduser()


def own_project_name() -> str:
    """Claude names a project folder after its working directory, every non-alphanumeric character as '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(Path(paths.__file__).resolve().parents[2]))


def _is_own(project: str) -> bool:
    own = own_project_name()
    return project == own or project.startswith(own + _OWN_WORKTREES)


def _blocks(message: dict[str, Any]) -> list[dict[str, Any]]:
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if not isinstance(content, list) or not all(isinstance(b, dict) for b in content):
        raise ValueError("session message 'content' is neither text nor a list of blocks")
    return content


def _is_librarian_call(block: dict[str, Any]) -> bool:
    command = (block.get("input") or {}).get("command")
    return block.get("name") == "Bash" and isinstance(command, str) and bool(_LIBRARIAN_COMMAND.search(command))


class _Session:
    """Filtering state that carries across the lines of one session."""

    def __init__(self) -> None:
        self.librarian_calls: set[str] = set()
        self.echo_started = False

    def evidence(self, line: dict[str, Any]) -> dict[str, Any] | None:
        """The role, timestamp and text to store for a message line, or None when nothing survives the filter."""
        message = line.get("message")
        role = message.get("role") if isinstance(message, dict) else None
        if role not in ("user", "assistant"):
            raise ValueError(f"session line has no usable role (got {role!r})")
        timestamp = line.get("timestamp")
        if not isinstance(timestamp, str):
            raise ValueError("session line has no 'timestamp'")
        texts: list[str] = []
        for block in _blocks(message):
            kind = block.get("type")
            if kind == "tool_use":
                if not isinstance(block.get("name"), str) or not isinstance(block.get("id"), str):
                    raise ValueError("session tool call has no 'name' or 'id'")
                if _is_librarian_call(block):
                    self.librarian_calls.add(block["id"])
                    self.echo_started = True
            elif kind == "tool_result":
                if block.get("tool_use_id") not in self.librarian_calls and isinstance(block.get("content"), str):
                    texts.append(block["content"])
            elif kind == "text":
                if not isinstance(block.get("text"), str):
                    raise ValueError("session text block has no 'text'")
                if role == "user" or not self.echo_started:
                    texts.append(block["text"])
        text = "\n".join(t for t in texts if t.strip())
        return {"role": role, "timestamp": timestamp, "text": text} if text else None


def _session_items(path: Path, project: str) -> Iterator[tuple[str, str | Exception]]:
    """(item id, content) for each evidence line; an Exception stands for a line that fails on its own."""
    session = _Session()
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        item = f"{path.stem}/{number}"
        try:
            line = json.loads(raw)
            if not isinstance(line, dict):
                raise ValueError("session line is not a JSON object")
            if line.get("type") not in ("user", "assistant"):
                continue  # summaries, snapshots and other bookkeeping lines carry no conversation
            kept = session.evidence(line)
        except ValueError as exc:
            yield item, exc
            continue
        if kept:
            kept |= {"session_id": path.stem, "project": project, "line": number}
            yield item, json.dumps(kept, ensure_ascii=False, sort_keys=True)


def stage(workspace: str) -> Stage:
    fetched: dict[str, tuple[str | Exception, str]] = {}

    def discover(conn: sqlite3.Connection) -> Iterator[tuple[str, str]]:
        root = projects_dir()
        if not root.is_dir():
            return
        for folder in sorted(p for p in root.iterdir() if p.is_dir() and not _is_own(p.name)):
            for path in sorted(folder.glob("*.jsonl")):
                for item, content in _session_items(path, folder.name):
                    if isinstance(content, str) and store.latest_content(conn, workspace, SOURCE, item) == content:
                        continue
                    fetched[item] = (content, folder.name)
                    yield SOURCE, item

    def process(conn: sqlite3.Connection, source: str, item: str) -> None:
        if item not in fetched:
            raise LookupError("session line was not read in this run; it is retried next Import")
        content, project = fetched.pop(item)
        if isinstance(content, Exception):
            raise content
        store.upsert(conn, workspace, SOURCE, item, content, origin_name=project, origin_kind="session")

    return Stage("fetch", process, discover, "fetched")
