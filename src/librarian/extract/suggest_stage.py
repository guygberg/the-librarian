"""The standalone Suggestions analysis: one call per unit, resumable, independent of Import.

Whether a unit needs a call is `suggestion_units` alone: only a succeeded row whose text, prompt and
schema hashes all still match skips it. Each unit is stored in one transaction (Suggestions,
Evidence, one `created` event each and the success marker), so an interrupted or failed unit leaves
no false success and no half-written Suggestions. Records, Tags, Persons and Links are never
written.
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from librarian import suggestion_lifecycle
from librarian.clock import utc_now_iso
from librarian.extract import candidates, runs, schema, units
from librarian.extract.stage import _hash
from librarian.ports import Extractor


@dataclass
class Counts:
    eligible: int = 0
    sent: int = 0
    succeeded: int = 0
    failed: int = 0
    deferred: int = 0
    created: int = 0
    empty: int = 0

    def line(self) -> str:
        return ", ".join(f"{name} {value}" for name, value in vars(self).items())


def eligible_units(
    conn: sqlite3.Connection, workspace: str, prompt_hash: str, schema_hash: str
) -> list[units.Unit]:
    """Units with no matching success, newest first."""
    done = {
        (key, text, prompt, schema_)
        for key, text, prompt, schema_ in conn.execute(
            "SELECT unit_key, text_hash, prompt_hash, schema_hash FROM suggestion_units"
            " WHERE workspace = ? AND status = 'succeeded'",
            (workspace,),
        )
    }
    distinct = {u.key: u for group in units.build(conn, workspace).values() for u in group}
    todo = [u for u in distinct.values() if (u.key, _hash(u), prompt_hash, schema_hash) not in done]
    return sorted(todo, key=lambda u: (-u.newest, u.key))


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()


def analyse(
    conn: sqlite3.Connection,
    workspace: str,
    suggester: Extractor,
    max_calls: int,
    cfg: dict[str, Any],
    dry_run: bool = False,
) -> Counts:
    """A dry run reads only, and never touches the suggester."""
    todo = eligible_units(
        conn, workspace, prompt_hash(suggester.prompt), schema.suggest_schema_hash()
    )
    limit = max(0, max_calls)
    counts = Counts(eligible=len(todo), deferred=max(0, len(todo) - limit))
    if dry_run:
        return counts
    for unit in todo[:limit]:
        counts.sent += 1
        _analyse_unit(conn, workspace, suggester, unit, cfg, counts)
    return counts


def _analyse_unit(conn, workspace, suggester, unit, cfg, counts: Counts) -> None:
    sent = candidates.pick_for_suggestions(conn, workspace, unit, cfg["import_staleness_days"])
    run_id = None
    try:
        run_id, result = runs.suggest_and_record(
            conn, workspace, suggester, suggester.meta, unit, sent, cfg["suggest_min_confidence"]
        )
        # A bad answer as a whole is a failure; a dropped single Suggestion is not.
        if any(r.piece == "result" for r in result.rejections):
            raise ValueError(result.rejections[-1].reason)
    except Exception:
        _mark(conn, workspace, unit, suggester, run_id, "failed", 0)
        counts.failed += 1
        return
    created = _store(conn, workspace, unit, suggester, run_id, result.suggestions)
    counts.succeeded += 1
    counts.created += created
    counts.empty += not result.suggestions


def _mark(conn, workspace, unit, suggester, run_id, status: str, count: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO suggestion_units (workspace, unit_key, text_hash, prompt_hash,"
        " schema_hash, run_id, status, suggestion_count, analysed_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            workspace,
            unit.key,
            _hash(unit),
            prompt_hash(suggester.prompt),
            schema.suggest_schema_hash(),
            run_id,
            status,
            count,
            utc_now_iso(),
        ),
    )


def _store(conn, workspace, unit, suggester, run_id, suggestions: list[dict]) -> int:
    now = utc_now_iso()
    conn.execute("BEGIN")
    try:
        created = 0
        by_ref = {s["ref"]: s for s in suggestions}
        seen: set[str] = set()
        for s in suggestions:
            if not s["evidence"]:
                raise ValueError("a Suggestion needs Evidence")
            suggestion_id = _insert(conn, workspace, run_id, s, by_ref, now, seen)
            if suggestion_id is None:  # the same Suggestion is already stored
                continue
            created += 1
            conn.executemany(
                "INSERT INTO suggestion_evidence (workspace, suggestion_id, revision_id, locator,"
                " quote) VALUES (?, ?, ?, ?, ?)",
                [
                    (workspace, suggestion_id, e["revision_id"], e["locator"], e["quote"])
                    for e in s["evidence"]
                ],
            )
            conn.execute(
                "INSERT INTO suggestion_events (workspace, suggestion_id, event, detail, at)"
                " VALUES (?, ?, 'created', ?, ?)",
                (workspace, suggestion_id, json.dumps({"run_id": run_id}), now),
            )
        _mark(conn, workspace, unit, suggester, run_id, "succeeded", len(suggestions))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return created


_PAYLOAD_KEYS = (
    "title", "body", "owner", "stated_deadline", "lifecycle", "link_type", "from", "to",
)  # fmt: skip


def _insert(conn, workspace, run_id, s, by_ref, now, seen: set[str]) -> int | None:
    """None when the same Suggestion already stands. One whose Evidence now cites other
    revisions has materially changed: the old one is superseded (unless accepted), and a new
    one made."""
    key = _dedupe_key(s, by_ref)
    if key in seen:  # the model said it twice in one answer
        return None
    seen.add(key)
    row = conn.execute(
        "SELECT id, status FROM suggestions WHERE workspace = ? AND dedupe_key = ?",
        (workspace, key),
    ).fetchone()
    if row:
        old_id, status = row
        revisions = {
            r
            for (r,) in conn.execute(
                "SELECT revision_id FROM suggestion_evidence WHERE suggestion_id = ?", (old_id,)
            )
        }
        if status == "accepted" or revisions == {e["revision_id"] for e in s["evidence"]}:
            return None
        suggestion_lifecycle.supersede(conn, workspace, [old_id], "source changed")
    payload = {k: s[k] for k in _PAYLOAD_KEYS if k in s}
    ends = {}
    for side in ("from", "to"):
        end = s.get(side)
        if end and "type" in end:
            ends[side] = (end["type"], end["id"])
    cur = conn.execute(
        "INSERT INTO suggestions (workspace, kind, link_type, payload, from_type,"
        " from_id, to_type, to_id, run_id, confidence, band, basis, reasoning, dedupe_key,"
        " created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            workspace,
            s["kind"],
            s.get("link_type"),
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            *ends.get("from", (None, None)),
            *ends.get("to", (None, None)),
            run_id,
            s["confidence"],
            s["band"],
            s["basis"],
            s["reasoning"],
            key,
            now,
        ),
    )
    return cur.lastrowid


def _dedupe_key(s: dict, by_ref: dict[str, dict]) -> str:
    """What the Suggestion proposes, with an end that names a new Tag/Item by that thing's title."""

    def end(e: dict) -> Any:
        if "ref" in e:
            target = by_ref[e["ref"]]
            return [target["kind"], target["title"].casefold()]
        return [e["type"], e["id"]]

    if s["kind"] == "link":
        parts: list[Any] = ["link", s["link_type"], end(s["from"]), end(s["to"])]
    elif s["kind"] == "new_tag":
        parts = ["new_tag", s["title"].casefold()]
    else:
        owner = s.get("owner")
        parts = ["new_item", s["title"].casefold(), owner]
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()
