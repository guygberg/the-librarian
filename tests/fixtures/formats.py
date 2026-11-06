"""Writers for the made-up source formats: Slack replay pages, Claude sessions, recordings.

Everything is deterministic: callers pass explicit timestamps and a seeded Random.
"""

import json
from pathlib import Path

PAGE_SIZE = 200


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def ts(epoch: int, n: int = 0) -> str:
    return f"{epoch}.{n:06d}"


def slack_message(user: str, text: str, ts_: str, thread_ts: str | None = None, files=None) -> dict:
    msg = {"type": "message", "user": user, "text": text, "ts": ts_}
    if thread_ts:
        msg["thread_ts"] = thread_ts
    if files:
        msg["files"] = files
    return msg


def write_slack_workspace(target: Path, url: str, users: list[dict], conversations: list[dict]):
    slack = target / "slack"
    write_json(slack / "auth.test.json", {"ok": True, "url": url, "team": "Acme Test", "user_id": users[0]["id"]})
    write_json(slack / "users.list.json", {"ok": True, "members": users})
    write_json(
        slack / "conversations.list.json",
        {"ok": True, "channels": conversations, "response_metadata": {"next_cursor": ""}},
    )


def write_slack_history(target: Path, channel: str, messages: list[dict]) -> None:
    """Newest-first pages of at most PAGE_SIZE, chained by cursor like conversations.history."""
    newest_first = sorted(messages, key=lambda m: m["ts"], reverse=True)
    chunks = [newest_first[i : i + PAGE_SIZE] for i in range(0, len(newest_first), PAGE_SIZE)] or [[]]
    for n, chunk in enumerate(chunks):
        more = n + 1 < len(chunks)
        write_json(
            target / "slack" / "history" / channel / f"page-{n}.json",
            {
                "ok": True,
                "messages": chunk,
                "has_more": more,
                "response_metadata": {"next_cursor": f"{channel}-cursor-{n + 1}" if more else ""},
            },
        )


def write_slack_replies(target: Path, channel: str, thread_ts: str, messages: list[dict]) -> None:
    write_json(
        target / "slack" / "replies" / channel / f"{thread_ts}.json",
        {"ok": True, "messages": messages, "has_more": False},
    )


def session_line(role: str, timestamp: str, content: list[dict] | str, **extra) -> dict:
    return {"type": role, "timestamp": timestamp, "message": {"role": role, "content": content}, **extra}


def write_session(target: Path, project_dir: str, session_id: str, lines: list[dict]) -> None:
    path = target / "claude" / "projects" / project_dir / f"{session_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(l, ensure_ascii=False, sort_keys=True) + "\n" for l in lines))


def segment(start: float, end: float, text: str, rng) -> dict:
    words = text.split()
    return {
        "start": start,
        "end": end,
        "text": text,
        "avg_logprob": round(-rng.uniform(0.05, 0.6), 4),
        "no_speech_prob": round(rng.uniform(0.0, 0.1), 4),
        "compression_ratio": round(rng.uniform(1.0, 1.8), 4),
        "tokens": [{"text": w, "p": round(rng.uniform(0.6, 1.0), 4)} for w in words],
    }


def write_recording(folder: Path, name: str, segments: list[dict]) -> None:
    """Extensionless placeholder `name` plus a sidecar `name.transcript.json`."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(b"placeholder recording, not real media\n")
    write_json(folder / f"{name}.transcript.json", {"segments": segments})
