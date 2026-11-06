"""Run one extraction call, validate it, and keep the run record and what was rejected."""

import hashlib
import sqlite3
from dataclasses import dataclass
from typing import Any

from librarian.clock import utc_now_iso
from librarian.extract import schema, validate
from librarian.ports import Extractor


@dataclass(frozen=True)
class RunMeta:
    """What the engine says about itself; the real one reads it from the pinned `claude` install."""

    model: str
    claude_code_version: str
    prompt: str


def extract_and_record(
    conn: sqlite3.Connection,
    workspace: str,
    extractor: Extractor,
    meta: RunMeta,
    unit_key: str,
    unit_text: str,
    candidates: list[dict[str, Any]],
    locators: set[str],
) -> validate.Validated:
    failure = None
    try:
        text = extractor.extract(unit_key, unit_text, candidates)
    except Exception as exc:
        if not hasattr(
            exc, "stage"
        ):  # only a failure that carries its stage and envelope is a run to keep
            raise
        failure, text = exc, ""
    # The real engine hands back the structured output but remembers the whole envelope.
    envelope = failure.envelope if failure else getattr(text, "raw", text)
    result = validate.Validated()
    if failure:
        result.rejections.append(
            validate.Rejection(failure.stage, "extraction_failed", failure.error)
        )
    else:
        result = validate.validate(text, unit_text, {c["id"] for c in candidates}, locators)
    conn.execute("BEGIN")
    try:
        run_id = conn.execute(
            "INSERT INTO extraction_runs (workspace, unit_key, model, claude_code_version,"
            " prompt_hash, schema_hash, envelope, accepted, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                workspace,
                unit_key,
                meta.model,
                meta.claude_code_version,
                hashlib.sha256(meta.prompt.encode()).hexdigest(),
                schema.schema_hash(),
                envelope,
                len(result.records),
                utc_now_iso(),
            ),
        ).lastrowid
        conn.executemany(
            "INSERT INTO extraction_rejections (workspace, run_id, piece, reason, detail)"
            " VALUES (?, ?, ?, ?, ?)",
            [(workspace, run_id, r.piece, r.reason, r.detail) for r in result.rejections],
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    if failure:
        raise failure
    return result


def list_runs(conn: sqlite3.Connection, workspace: str) -> list[dict[str, Any]]:
    runs = []
    for row in conn.execute(
        "SELECT id, unit_key, model, claude_code_version, prompt_hash, schema_hash, envelope,"
        " accepted, created_at FROM extraction_runs WHERE workspace = ? ORDER BY id",
        (workspace,),
    ).fetchall():
        rejections = [
            {"piece": p, "reason": r, "detail": d}
            for p, r, d in conn.execute(
                "SELECT piece, reason, detail FROM extraction_rejections"
                " WHERE run_id = ? ORDER BY id",
                (row[0],),
            )
        ]
        keys = (
            "id",
            "unit_key",
            "model",
            "claude_code_version",
            "prompt_hash",
            "schema_hash",
            "envelope",
            "accepted_records",
            "created_at",
        )
        runs.append({**dict(zip(keys, row, strict=True)), "rejected": rejections})
    return runs
