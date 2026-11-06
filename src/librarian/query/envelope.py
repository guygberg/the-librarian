"""The one answer envelope every answer command returns.

Its keys: warnings, resolved, records, evidence, freshness.

`warnings` comes first on purpose: an answer starts with it.
Commands add their own keys after the five.
"""

import sqlite3
from datetime import datetime
from typing import Any

from librarian import locator, store
from librarian.query import core

KEYS = ("warnings", "resolved", "records", "evidence", "freshness")
DAY = 86_400
WORKSPACE_BASELINE = {"project": None, "baseline": "whole workspace"}


def _overdue_days(cfg: dict[str, Any], source: str) -> int:
    return cfg.get(f"source_overdue_days_{source}", cfg["source_overdue_days"])


def freshness(
    conn: sqlite3.Connection, workspace: str, cfg: dict[str, Any], at: datetime
) -> dict[str, Any]:
    """Last successful Import per configured source, and the warnings a missing or old one earns."""
    last = dict(
        conn.execute(
            # Recordings are the `drive` source everywhere a person sees it;
            # the importer calls them `recording`.
            "SELECT CASE s.source WHEN 'recording' THEN 'drive' ELSE s.source END, MAX(r.ended_at)"
            " FROM import_item_stages s JOIN import_runs r ON r.id = s.run_id"
            " WHERE s.workspace = ? AND r.status = 'finished' GROUP BY 1",
            (workspace,),
        )
    )
    overall = conn.execute(
        "SELECT MAX(ended_at) FROM import_runs WHERE workspace = ? AND status = 'finished'",
        (workspace,),
    ).fetchone()[0]
    sources = {}
    for source in cfg["import_sources"]:
        ended = last.get(source)
        days = _overdue_days(cfg, source)
        # Import times are written in local time without a zone;
        # `astimezone()` makes them comparable with `at`.
        overdue = (
            ended is not None
            and (at - datetime.fromisoformat(ended).astimezone()).total_seconds() > days * DAY
        )
        sources[source] = {
            "last_import_finished_at": ended,
            "overdue": overdue,
            "overdue_after_days": days,
        }
    return {"last_import_finished_at": overall, "sources": sources}


def warnings_for(fresh: dict[str, Any]) -> list[dict[str, str]]:
    out = []
    for source, state in fresh["sources"].items():
        if state["last_import_finished_at"] is None:
            out.append(
                {
                    "code": "source_never_imported",
                    "source": source,
                    "message": f"{source} has never been imported",
                }
            )
        elif state["overdue"]:
            message = (
                f"{source} was last imported {state['last_import_finished_at']}, "
                f"over {state['overdue_after_days']} days ago"
            )
            out.append({"code": "source_overdue", "source": source, "message": message})
    return out


def evidence_for(
    conn: sqlite3.Connection, workspace: str, record_ids: list[int]
) -> list[dict[str, Any]]:
    if not record_ids:
        return []
    marks = ", ".join("?" * len(record_ids))
    gone = store.gone_ids(conn, workspace, "slack")
    return [
        {
            "record_id": record_id,
            "source": locator.parse(loc).source,
            "locator": loc,
            "quote": quote,
            "role": role,
            "retrieved_at": retrieved,
            **({"gloss": gloss} if gloss else {}),
            **({"gone_from_source": True} if store.evidence_is_gone(loc, gone) else {}),
        }
        for record_id, loc, quote, role, retrieved, gloss in conn.execute(
            "SELECT record_id, locator, quote, role, retrieved_at, gloss FROM evidence"
            f" WHERE workspace = ? AND record_id IN ({marks}) ORDER BY record_id, id",
            (workspace, *record_ids),
        )
    ]


def build(
    conn: sqlite3.Connection,
    workspace: str,
    cfg: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    at: datetime | None = None,
    resolved: dict[str, Any] = WORKSPACE_BASELINE,
    evidence: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """`records` are current views; their Evidence moves to the top-level `evidence` list.

    The list is keyed by record_id. Pass `evidence` for answers whose evidence is not a
    Record's (search passages). `resolved` names the project or baseline the answer was
    computed over.
    """
    fresh = freshness(conn, workspace, cfg, at or core.now())
    if evidence is None:
        evidence = evidence_for(conn, workspace, [r["id"] for r in records])
    slim = [{k: v for k, v in r.items() if k != "evidence"} for r in records]
    return {
        "warnings": warnings_for(fresh),
        "resolved": resolved,
        "records": slim,
        "evidence": evidence,
        "freshness": fresh,
        **extra,
    }
