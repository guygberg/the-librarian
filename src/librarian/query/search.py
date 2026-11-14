"""Search Source items. Read-only: takes a connection from `db.connect_ro`."""

import json
import sqlite3
from collections.abc import Callable

from librarian import config, locator, textsearch
from librarian.link import people as identities
from librarian.query import core, envelope

SNIPPET_CHARS = 160


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SNIPPET_CHARS else text[:SNIPPET_CHARS].rstrip() + "…"


def _record_ids(
    conn: sqlite3.Connection, workspace: str, matches: Callable[[str], bool], limit: int
) -> list[int]:
    """Records are matched here, not in the full-text index.

    They change through many writers and a work memory bank holds few. Text is the title,
    body, reasoning, Evidence quotes; title matches rank first.
    """
    extra: dict[int, list[str]] = {}
    for table, column in (("evidence", "quote"),):
        for record_id, text in conn.execute(
            f"SELECT record_id, {column} FROM {table} WHERE workspace = ?", (workspace,)
        ):
            extra.setdefault(record_id, []).append(text)
    edits = {}
    for rid, event, detail in conn.execute(
        "SELECT record_id, event, detail FROM record_events"
        " WHERE workspace = ? AND event IN ('edit', 'rename') ORDER BY id",
        (workspace,),
    ):
        change = json.loads(detail)
        edits.setdefault(rid, {}).update(
            {"title": change["title"], "body": change["body"]}
            if event == "edit"
            else {"title": change["to"]}
        )
    titled, other = [], []
    for record_id, title, body, reasoning in conn.execute(
        "SELECT id, title, body, reasoning FROM items WHERE workspace = ? ORDER BY id",
        (workspace,),
    ):
        title = edits.get(record_id, {}).get("title", title)
        body = edits.get(record_id, {}).get("body", body)
        if matches(title):
            titled.append(record_id)
        elif matches(" ".join([title, body, reasoning or "", *extra.get(record_id, [])])):
            other.append(record_id)
    return (titled + other)[:limit]


def _people(conn: sqlite3.Connection, workspace: str, matches: Callable[[str], bool]) -> list[dict]:
    people = {
        pid: {
            "person_id": pid,
            "name": name,
            "aliases": [],
            "slack_id": slack_id,
            "email": email,
            "role": role,
            "department": department,
        }
        for pid, name, slack_id, email, role, department in conn.execute(
            "SELECT id, name, slack_id, email, role, department FROM people"
            " WHERE workspace = ? ORDER BY id",
            (workspace,),
        )
    }
    for pid, alias in identities.alias_rows(conn, workspace):
        people[pid]["aliases"].append(alias)
    return [
        p
        for p in people.values()
        if any(
            matches(label)
            for label in (
                p["name"],
                *p["aliases"],
                p["slack_id"],
                p["email"],
                p["role"],
                p["department"],
            )
            if label
        )
    ]


def search(conn: sqlite3.Connection, workspace: str, query: str, limit: int = 20) -> dict:
    """Matching Records are the envelope's `records`.

    Their Evidence, then the raw passages (Source items, role `match`, no record_id), make
    up its `evidence`. People are an extra `people` key.
    """
    matches = textsearch.matcher(query)
    cfg = config.load()
    at = core.now()
    views = [
        core.current_view(conn, workspace, rid, cfg, at)
        for rid in _record_ids(conn, workspace, matches, limit)
    ]
    expression = textsearch.match_expression(query)
    rows = []
    if expression:
        rows = conn.execute(
            "SELECT s.source, s.stable_id, s.original, i.origin_name, i.gone,"
            " (SELECT MAX(fetched_at) FROM source_item_revisions WHERE source_item_id = i.id)"
            " FROM source_search s JOIN source_items i ON i.id = s.source_item_id"
            " WHERE source_search MATCH ? AND s.workspace = ? ORDER BY s.rank LIMIT ?",
            (expression, workspace, limit),
        ).fetchall()
    passages = [
        {
            "record_id": None,
            "source": source,
            "locator": str(locator.Locator(source, stable_id)),
            "quote": _snippet(original),
            "role": "match",
            "retrieved_at": fetched,
            "origin_name": origin_name,
            "gone_from_source": bool(gone),
        }
        for source, stable_id, original, origin_name, gone, fetched in rows
    ]
    evidence = envelope.evidence_for(conn, workspace, [v["id"] for v in views]) + passages
    return envelope.build(
        conn,
        workspace,
        cfg,
        views,
        at=at,
        evidence=evidence,
        people=_people(conn, workspace, matches),
    )
