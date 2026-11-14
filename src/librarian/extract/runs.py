"""Run one extraction call, validate it, and keep the run record and what was rejected."""

import hashlib
import sqlite3
from dataclasses import dataclass
from typing import Any

from librarian.clock import utc_now_iso
from librarian.extract import schema, suggest_validate, validate
from librarian.extract.units import Unit
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
    text, envelope, failure = _call(extractor, unit_key, unit_text, candidates)
    result = validate.Validated()
    if failure:
        result.rejections.append(_failed(failure))
    else:
        result = validate.validate(text, unit_text, {c["id"] for c in candidates}, locators)
    _store_run(
        conn, workspace, unit_key, meta, schema.schema_hash(), "extraction", envelope,
        len(result.records), result.rejections,
    )  # fmt: skip
    if failure:
        raise failure
    return result


def suggest_and_record(
    conn: sqlite3.Connection,
    workspace: str,
    extractor: Extractor,
    meta: RunMeta,
    unit: Unit,
    candidates: list[dict[str, Any]],
    min_confidence: int,
) -> tuple[int, suggest_validate.SuggestValidated]:
    """One Suggestions call, validated; returns the run id with the result. Stores only the run and
    what was rejected: the caller stores accepted Suggestions against the run id."""
    text, envelope, failure = _call(extractor, unit.key, unit.text, candidates)
    result = suggest_validate.SuggestValidated()
    if failure:
        result.rejections.append(_failed(failure))
    else:
        result = suggest_validate.validate(text, unit, candidates, min_confidence)
    run_id = _store_run(
        conn, workspace, unit.key, meta, schema.suggest_schema_hash(), "suggestions", envelope,
        len(result.suggestions), result.rejections,
    )  # fmt: skip
    if failure:
        raise failure
    return run_id, result


def _call(extractor: Extractor, unit_key: str, unit_text: str, candidates: list[dict[str, Any]]):
    try:
        text = extractor.extract(unit_key, unit_text, candidates)
    except Exception as exc:
        if not hasattr(
            exc, "stage"
        ):  # only a failure that carries its stage and envelope is a run to keep
            raise
        return "", exc.envelope, exc
    # The real engine hands back the structured output but remembers the whole envelope.
    return text, getattr(text, "raw", text), None


def _failed(failure: Exception) -> validate.Rejection:
    return validate.Rejection(failure.stage, "extraction_failed", failure.error)


def _store_run(
    conn: sqlite3.Connection,
    workspace: str,
    unit_key: str,
    meta: RunMeta,
    schema_hash: str,
    purpose: str,
    envelope: str,
    accepted: int,
    rejections: list[validate.Rejection],
) -> int:
    conn.execute("BEGIN")
    try:
        run_id = conn.execute(
            "INSERT INTO extraction_runs (workspace, unit_key, model, claude_code_version,"
            " prompt_hash, schema_hash, purpose, envelope, accepted, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                workspace,
                unit_key,
                meta.model,
                meta.claude_code_version,
                hashlib.sha256(meta.prompt.encode()).hexdigest(),
                schema_hash,
                purpose,
                envelope,
                accepted,
                utc_now_iso(),
            ),
        ).lastrowid
        conn.executemany(
            "INSERT INTO extraction_rejections (workspace, run_id, piece, reason, detail)"
            " VALUES (?, ?, ?, ?, ?)",
            [(workspace, run_id, r.piece, r.reason, r.detail) for r in rejections],
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return run_id


def list_runs(conn: sqlite3.Connection, workspace: str) -> list[dict[str, Any]]:
    runs = []
    for row in conn.execute(
        "SELECT id, unit_key, model, claude_code_version, prompt_hash, schema_hash, envelope,"
        " accepted, created_at FROM extraction_runs WHERE workspace = ? AND purpose = 'extraction'"
        " ORDER BY id",
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
