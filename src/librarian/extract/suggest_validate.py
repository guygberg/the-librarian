"""Decide what the Suggestions analysis accepts from one model answer. Never stores; only rejects.

Granularity: bad JSON drops the whole answer; a bad Suggestion drops that Suggestion; a bad Evidence
item drops only itself, and a Suggestion left with none is dropped. Every end of a Link must be a
candidate that was sent or a kept new Tag/Item of the same answer, so untrusted output cannot name a
Record or Person the workspace did not offer.
"""

import json
from datetime import date
from typing import Any

from librarian import locator
from librarian.extract import schema
from librarian.extract.validate import Rejection

_COMMON = {"ref", "kind", "confidence", "basis", "reasoning", "evidence"}
_ALLOWED = {
    "new_tag": _COMMON | {"title", "body"},
    "new_item": _COMMON | {"title", "body", "owner", "stated_deadline", "lifecycle"},
    "link": _COMMON | {"link_type", "from", "to"},
}
# What each Link type may join; mirrors the person/record rules of extraction Links.
_FROM_RECORD_ONLY = {"belongs_to", "blocks", "supersedes", "related_to", "contradicts", "owner"}
_TO_RECORD_ONLY = {"belongs_to", "blocks", "supersedes", "related_to", "contradicts"}
_TO_PERSON_ONLY = {"owner"}


class SuggestValidated:
    def __init__(self) -> None:
        self.suggestions: list[dict[str, Any]] = []
        self.rejections: list[Rejection] = []


def band(confidence: int) -> str:
    return "high" if confidence >= 80 else "medium" if confidence >= 60 else "low"


def validate(
    raw: str,
    unit: Any,
    candidates: list[dict[str, Any]],
    min_confidence: int,
) -> SuggestValidated:
    """`unit` is the extraction Unit sent: its `revisions` name the exact revision of every item."""
    out = SuggestValidated()
    try:
        data = json.loads(raw)
    except ValueError as err:
        out.rejections.append(Rejection("result", "invalid_json", str(err)))
        return out
    items = data.get("suggestions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        out.rejections.append(
            Rejection("result", "bad_shape", "expected an object with a `suggestions` list")
        )
        return out

    ids = {
        kind: {c["id"] for c in candidates if c["kind"] == kind}
        for kind in ("tag", "action_item", "person")
    }
    ids["record"] = ids["tag"] | ids["action_item"]
    kept: dict[int, dict[str, Any]] = {}
    new_refs: dict[str, str] = {}  # ref of a kept new Tag/Item -> its kind
    seen: set[str] = set()
    links: list[tuple[int, dict]] = []
    for i, item in enumerate(items):
        piece = f"suggestions[{i}]"
        problem = _check_common(item, seen)
        if problem:
            out.rejections.append(Rejection(piece, *problem))
            continue
        seen.add(item["ref"])
        problem = _check_kind(item, ids)
        if problem:
            out.rejections.append(Rejection(piece, *problem))
            continue
        evidence = _check_evidence(item["evidence"], piece, unit, out)
        if not evidence:
            out.rejections.append(Rejection(piece, "no_evidence", "no valid Evidence left"))
            continue
        confidence = min(100, max(0, item["confidence"]))
        if item["basis"] == "inferred":
            confidence = min(confidence, schema.INFERRED_CAP)
        if confidence < min_confidence:
            out.rejections.append(
                Rejection(piece, "below_confidence_floor", f"{confidence} < {min_confidence}")
            )
            continue
        clean = {**item, "confidence": confidence, "band": band(confidence), "evidence": evidence}
        if item["kind"] == "link":
            links.append((i, clean))
        else:
            kept[i] = clean
            new_refs[item["ref"]] = item["kind"]
    for i, link in links:
        problem = _check_link(link, ids, new_refs)
        if problem:
            out.rejections.append(Rejection(f"suggestions[{i}]", *problem))
        else:
            kept[i] = link
    out.suggestions = [kept[i] for i in sorted(kept)]
    return out


def _check_common(item: Any, seen: set[str]) -> tuple[str, str] | None:
    if not isinstance(item, dict):
        return "bad_shape", "suggestion is not an object"
    ref = item.get("ref")
    if not (isinstance(ref, str) and ref):
        return "bad_shape", "missing ref"
    if ref in seen:
        return "duplicate_ref", ref
    if item.get("kind") not in schema.SUGGEST_KINDS:
        return "bad_enum", f"kind={item.get('kind')!r}"
    extra = set(item) - _ALLOWED[item["kind"]]
    if extra:
        return "bad_shape", f"`{sorted(extra)[0]}` does not belong on a {item['kind']}"
    if item.get("basis") not in schema.SUGGEST_BASES:
        return "bad_enum", f"basis={item.get('basis')!r}"
    # bool is an int in Python, but `true` is not a confidence.
    if type(item.get("confidence")) is not int:
        return "bad_confidence", repr(item.get("confidence"))
    if not (isinstance(item.get("reasoning"), str) and item["reasoning"].strip()):
        return "bad_shape", "missing reasoning"
    if not isinstance(item.get("evidence"), list):
        return "no_evidence", "evidence is not a list"
    return None


def _check_kind(item: dict, ids: dict[str, set[int]]) -> tuple[str, str] | None:
    kind = item["kind"]
    if kind == "link":
        if item.get("link_type") not in schema.LINK_TYPES:
            return "bad_enum", f"link_type={item.get('link_type')!r}"
        if "from" not in item or "to" not in item:
            return "bad_shape", "link needs `from` and `to`"
        return None
    if not (isinstance(item.get("title"), str) and item["title"].strip()):
        return "bad_shape", "missing title"
    if kind == "new_tag":
        return None
    if item.get("lifecycle") not in schema.SUGGEST_LIFECYCLES:
        return "bad_enum", f"lifecycle={item.get('lifecycle')!r}"
    if "stated_deadline" in item:
        try:
            date.fromisoformat(item["stated_deadline"])
        except (TypeError, ValueError):
            return "bad_date", repr(item["stated_deadline"])
    if "owner" in item:
        owner = item["owner"]
        if not isinstance(owner, dict) or len(owner) != 1:
            return "bad_shape", f"owner={owner!r}"
        if "id" in owner:
            if owner["id"] not in ids["person"]:
                return "unknown_id", f"person {owner['id']!r} was not sent"
        elif not (isinstance(owner.get("raw_name"), str) and owner["raw_name"].strip()):
            return "bad_shape", f"owner={owner!r}"
    return None


def _check_evidence(items: list, piece: str, unit: Any, out: SuggestValidated) -> list[dict]:
    good = []
    for j, ev in enumerate(items):
        problem = _check_one_evidence(ev, unit)
        if isinstance(problem, tuple):
            out.rejections.append(Rejection(f"{piece}.evidence[{j}]", *problem))
        else:
            good.append(problem)
    return good


def _check_one_evidence(ev: Any, unit: Any) -> dict | tuple[str, str]:
    if not isinstance(ev, dict) or not isinstance(ev.get("quote"), str) or not ev["quote"].strip():
        return "bad_shape", "evidence needs a quote"
    try:
        parsed = locator.parse(ev.get("locator") or "")
    except ValueError as err:
        return "bad_locator", str(err)
    found = unit.revisions.get(f"{parsed.source}:{parsed.stable_id}")
    if found is None:
        return "bad_locator", f"{ev['locator']!r} was not sent"
    revision_id, text = found
    if ev["quote"] not in text:  # literal: the person is shown exactly this text
        return "quote_not_found", ev["quote"][:80]
    return {"revision_id": revision_id, "locator": str(parsed), "quote": ev["quote"]}


def _check_link(
    link: dict, ids: dict[str, set[int]], new_refs: dict[str, str]
) -> tuple[str, str] | None:
    kind = link["link_type"]
    ends = {}
    for side in ("from", "to"):
        end = link[side]
        if not isinstance(end, dict) or len(end) not in (1, 2):
            return "bad_link_end", f"{side}={end!r}"
        if "ref" in end:
            if len(end) != 1 or end["ref"] not in new_refs:
                return "bad_ref", f"{side}={end!r}"
            ends[side] = "record"
        elif end.get("type") in ("record", "person") and len(end) == 2:
            if end.get("id") not in ids[end["type"]]:
                return "unknown_id", f"{side}={end!r} was not sent"
            ends[side] = end["type"]
        else:
            return "bad_link_end", f"{side}={end!r}"
    if ends["from"] != "record" and kind in _FROM_RECORD_ONLY:
        return "bad_link_end", f"{kind} cannot start at a person"
    if ends["to"] == "record" and kind in _TO_PERSON_ONLY:
        return "bad_link_end", f"{kind} must end at a person"
    if ends["to"] == "person" and kind in _TO_RECORD_ONLY:
        return "bad_link_end", f"{kind} cannot end at a person"
    if ends["from"] == "person" and ends["to"] == "person":
        return "bad_link_end", "a Link needs a Record at one end"
    return None
