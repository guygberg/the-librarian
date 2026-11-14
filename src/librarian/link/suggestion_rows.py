"""Pending Suggestions as Review rows. Read-only: acting on one is `suggestion_actions`.

A Suggestion is never forced into `review_entries` (its `record_id` needs an existing Record);
the Review answer merges both kinds of row instead."""

import json
import sqlite3
from typing import Any
from urllib.parse import parse_qs

from librarian import config
from librarian.link.errors import Invalid

BANDS = ("high", "medium", "low")
SORTS = ("confidence", "newest")
MARKS = {
    "new_tag": "suggested new tag",
    "new_item": "suggested new item",
    "link": "suggested link",
}
_PAYLOAD = ("title", "body", "owner", "lifecycle", "stated_deadline")
_TABLES = {"record": ("records", "title"), "person": ("persons", "name")}


def parse_query(query: str) -> dict[str, Any]:
    """The validated filters of a Review request; a bad one is a 400, never silently ignored."""
    raw = parse_qs(query, keep_blank_values=True)
    for name, values in raw.items():
        if name in ("min_confidence", "band", "sort") and len(values) != 1:
            raise Invalid(400, f"{name} must be given once")
    out: dict[str, Any] = {"min_confidence": None, "band": None, "sort": "confidence"}
    if "min_confidence" in raw:
        text = raw["min_confidence"][0]
        if not text.isascii() or not text.isdigit() or int(text) > 100:
            raise Invalid(400, "min_confidence must be an integer from 0 to 100")
        out["min_confidence"] = int(text)
    if "band" in raw:
        if raw["band"][0] not in BANDS:
            raise Invalid(400, f"band must be one of {', '.join(BANDS)}")
        out["band"] = raw["band"][0]
    if "sort" in raw:
        if raw["sort"][0] not in SORTS:
            raise Invalid(400, f"sort must be one of {', '.join(SORTS)}")
        out["sort"] = raw["sort"][0]
    return out


def pending(
    conn: sqlite3.Connection,
    workspace: str,
    min_confidence: int | None,
    band: str | None,
    sort: str,
) -> list[dict[str, Any]]:
    """Pending Suggestions at or above the floor: the one given, else the configured hide floor."""
    floor = config.load()["suggest_auto_hide_below"] if min_confidence is None else min_confidence
    order = (
        "created_at DESC, id DESC"
        if sort == "newest"
        else "confidence DESC, created_at DESC, id DESC"
    )
    sql = (
        "SELECT id, kind, link_type, payload, from_type, from_id, to_type, to_id, confidence,"
        " band, basis, reasoning, created_at FROM suggestions"
        " WHERE workspace = ? AND status = 'pending' AND confidence >= ?"
        + (" AND band = ?" if band else "")
        + f" ORDER BY {order}"
    )
    args = (workspace, floor, *([band] if band else []))
    return [_row(conn, workspace, *r) for r in conn.execute(sql, args).fetchall()]


def _row(conn, workspace, id_, kind, link_type, payload, from_type, from_id, to_type, to_id, *rest):
    confidence, band, basis, reasoning, created_at = rest
    payload = json.loads(payload)
    row: dict[str, Any] = {
        "type": "suggestion",
        "id": id_,
        "kind": kind,
        "mark": MARKS[kind],
        "confidence": confidence,
        "band": band,
        "basis": basis,
        "reasoning": reasoning,
        "created_at": created_at,
        **{k: payload[k] for k in _PAYLOAD if k in payload},
        "evidence": _evidence(conn, workspace, id_),
    }
    if kind == "link":
        row["link_type"] = link_type
        row["from"] = _end(conn, from_type, from_id, payload["from"] if "from" in payload else None)
        row["to"] = _end(conn, to_type, to_id, payload["to"] if "to" in payload else None)
    return row


def _end(conn, end_type, end_id, named):
    """A named existing end, or the new Tag/Item this Suggestion proposes alongside."""
    if end_type is None:
        return {"type": named["kind"], "title": named["title"]}
    table, column = _TABLES[end_type]
    found = conn.execute(f"SELECT {column} FROM {table} WHERE id = ?", (end_id,)).fetchone()
    return {"type": end_type, "id": end_id, "title": found[0] if found else None}


def _evidence(conn, workspace, suggestion_id):
    """Exact identities to open the source sheet: kind, stable id, revision, locator, quote."""
    return [
        {
            "source": source,
            "stable_id": stable_id,
            "revision": revision,
            "locator": locator,
            "quote": quote,
        }
        for source, stable_id, revision, locator, quote in conn.execute(
            "SELECT i.source, i.stable_id, r.revision, e.locator, e.quote"
            " FROM suggestion_evidence e JOIN source_item_revisions r ON r.id = e.revision_id"
            " JOIN source_items i ON i.id = r.source_item_id"
            " WHERE e.workspace = ? AND e.suggestion_id = ? ORDER BY e.id",
            (workspace, suggestion_id),
        )
    ]
