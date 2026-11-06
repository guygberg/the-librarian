"""Decide what the importer accepts from one extraction result. Never stores; rejects and reports.

Granularity: bad JSON drops the whole result; a bad Record field drops that Record; a bad Evidence
item or Link drops only that piece. A Record left with no Evidence is dropped too.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from librarian import locator
from librarian.extract import schema

_SLACK_USER = re.compile(r"^[UW][A-Z0-9]{2,}$")
# Link types whose end must be a Record / a person.
_RECORD_ONLY = {"belongs_to", "blocks", "supersedes", "related_to"}
_PERSON_ONLY = {"owner"}


@dataclass
class Rejection:
    piece: str
    reason: str
    detail: str = ""


@dataclass
class Validated:
    records: list[dict[str, Any]] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)


def normalise(text: str) -> str:
    return " ".join(text.split())


def validate(raw: str, unit_text: str, candidate_ids: set[int], locators: set[str]) -> Validated:
    """`locators` are the `<source>:<stable_id>` of the Source items sent (a `#part` is not part of it)."""
    out = Validated()
    try:
        data = json.loads(raw)
    except ValueError as err:
        out.rejections.append(Rejection("result", "invalid_json", str(err)))
        return out
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        out.rejections.append(Rejection("result", "bad_shape", "expected an object with a `records` list"))
        return out

    sent_text = normalise(unit_text)
    kept: list[tuple[str, dict]] = []  # (piece, record), in order
    refs: set[str] = set()
    for i, rec in enumerate(records):
        piece = f"records[{i}]"
        problem = _check_record(rec, candidate_ids, refs)
        if problem:
            out.rejections.append(Rejection(piece, *problem))
            continue
        evidence = _check_evidence(rec["evidence"], piece, sent_text, locators, out)
        if not evidence:
            out.rejections.append(Rejection(piece, "no_evidence", "no valid Evidence left"))
            continue
        refs.add(rec["ref"])
        kept.append((piece, {**rec, "evidence": evidence}))

    for piece, rec in kept:
        _check_ends(rec, piece, candidate_ids, refs, out)
        out.records.append(rec)
    return out


def _check_record(rec: Any, candidate_ids: set[int], refs: set[str]) -> tuple[str, str] | None:
    if not isinstance(rec, dict):
        return "bad_shape", "record is not an object"
    ref, kind = rec.get("ref"), rec.get("kind")
    if not (isinstance(ref, str) and ref):
        return "bad_shape", "missing ref"
    if ref in refs:
        return "duplicate_ref", ref
    if not (isinstance(rec.get("title"), str) and rec["title"].strip()):
        return "bad_shape", "missing title"
    for key, allowed in (("kind", schema.KINDS), ("lifecycle", schema.LIFECYCLES), ("basis", schema.BASES)):
        if rec.get(key) not in allowed:
            return "bad_enum", f"{key}={rec.get(key)!r}"
    if "commitment" in rec and rec["commitment"] not in schema.COMMITMENTS:
        return "bad_enum", f"commitment={rec['commitment']!r}"
    only = {"commitment": "action_item", "owner": "action_item", "stated_deadline": "action_item",
            "reasoning": "decision", "parent": "project"}
    for key, needed in only.items():
        if key in rec and kind != needed:
            return "bad_shape", f"`{key}` only belongs on a {needed}"
    if kind == "action_item" and "commitment" not in rec:
        return "bad_shape", "action item without commitment"
    match = rec.get("match")
    if not isinstance(match, dict) or match.get("decision") not in schema.ID_DECISIONS:
        return "bad_enum", f"match={match!r}"
    if match["decision"] == "new":
        if "id" in match:
            return "unknown_id", "a new Record cannot carry an id"
    elif match.get("id") not in candidate_ids:
        return "unknown_id", f"{match.get('id')!r} was not sent"
    if "stated_deadline" in rec:
        try:
            date.fromisoformat(rec["stated_deadline"])
        except (TypeError, ValueError):
            return "bad_date", repr(rec["stated_deadline"])
    if "owner" in rec and not _is_person(rec["owner"]):
        return "bad_shape", f"owner={rec['owner']!r}"
    if not isinstance(rec.get("evidence"), list):
        return "no_evidence", "evidence is not a list"
    return None


def _check_evidence(items: list, piece: str, sent_text: str, locators: set[str], out: Validated) -> list:
    good = []
    for j, ev in enumerate(items):
        where = f"{piece}.evidence[{j}]"
        problem = _check_one_evidence(ev, sent_text, locators)
        if problem:
            out.rejections.append(Rejection(where, *problem))
        else:
            good.append(ev)
    return good


def _check_one_evidence(ev: Any, sent_text: str, locators: set[str]) -> tuple[str, str] | None:
    if not isinstance(ev, dict) or not isinstance(ev.get("quote"), str) or not ev["quote"].strip():
        return "bad_shape", "evidence needs a quote"
    if ev.get("role") not in schema.EVIDENCE_ROLES:
        return "bad_enum", f"role={ev.get('role')!r}"
    try:
        parsed = locator.parse(ev.get("locator") or "")
    except ValueError as err:
        return "bad_locator", str(err)
    if f"{parsed.source}:{parsed.stable_id}" not in locators:
        return "bad_locator", f"{ev['locator']!r} was not sent"
    if normalise(ev["quote"]) not in sent_text:
        return "quote_not_found", ev["quote"][:80]
    return None


def _is_person(end: Any) -> bool:
    if not isinstance(end, dict) or len(end) != 1:
        return False
    (key, value), = end.items()
    if key == "slack_user":
        return isinstance(value, str) and bool(_SLACK_USER.match(value))
    if key == "name":
        return isinstance(value, str) and bool(value.strip())
    return key == "speaker" and value == "first_person"


def _is_record_end(end: Any, candidate_ids: set[int], refs: set[str]) -> bool:
    if not isinstance(end, dict) or len(end) != 1:
        return False
    if "ref" in end:
        return end["ref"] in refs
    return "id" in end and end["id"] in candidate_ids


def _check_ends(rec: dict, piece: str, candidate_ids: set[int], refs: set[str], out: Validated) -> None:
    """Drop (in place) the parent and Links whose ends were not sent or not accepted."""
    if "parent" in rec and not _is_record_end(rec["parent"], candidate_ids, refs):
        out.rejections.append(Rejection(f"{piece}.parent", "bad_link_end", repr(rec["parent"])))
        del rec["parent"]
    good = []
    for k, link in enumerate(rec.get("links", [])):
        problem = _check_link(link, candidate_ids, refs)
        if problem:
            out.rejections.append(Rejection(f"{piece}.links[{k}]", *problem))
        else:
            good.append(link)
    rec["links"] = good


def _check_link(link: Any, candidate_ids: set[int], refs: set[str]) -> tuple[str, str] | None:
    if not isinstance(link, dict) or link.get("type") not in schema.LINK_TYPES:
        return "bad_enum", f"link type={link.get('type') if isinstance(link, dict) else link!r}"
    end, kind = link.get("to"), link["type"]
    is_record = _is_record_end(end, candidate_ids, refs)
    is_person = _is_person(end)
    ok = (is_record and kind not in _PERSON_ONLY) or (is_person and kind not in _RECORD_ONLY)
    return None if ok else ("bad_link_end", f"{kind} -> {end!r}")
