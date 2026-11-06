"""Old and ownerless items in one Slack channel, one conversation day per group of Records.

Import with LIBRARIAN_NOW=NOW. The titles are the keys the tests look Records up by (see TITLES):
- 28 days ago (inside the 30-day fetch window): ownerless action "Review vendor contract", open question "Which region first", decision "Use Postgres".
- 20 days ago: action "Ship the report", cited as started and, later that day, as completed.
- 12 days ago: action "File taxes" extracted as done with no completion Evidence.
- 10 days ago: decisions "Launch on Dec 1" and "Launch on Dec 8", linked as contradicting.
- 3 days ago: action "Send the invoice", fresh; its message is edited in the second Import (inside the re-check
  window), whose extraction finds nothing.
"""

import json
from datetime import UTC, datetime

from fixtures import formats as f

NOW = 1_700_000_000
DAY = 86_400
URL = "https://acme-test.slack.com/"
USERS = [{"id": "U001", "name": "dana", "real_name": "Dana Levi"}]
CONVERSATIONS = [{"id": "C001", "name": "ops", "is_channel": True, "is_private": False, "num_members": 12}]

VENDOR, REGION, POSTGRES = "Review vendor contract", "Which region first", "Use Postgres"
SHIP, TAXES, DEC1, DEC8, INVOICE = "Ship the report", "File taxes", "Launch on Dec 1", "Launch on Dec 8", "Send the invoice"
TITLES = [VENDOR, REGION, POSTGRES, SHIP, TAXES, DEC1, DEC8, INVOICE]


def _ts(days: int, seconds_before: int) -> str:
    return f.ts(NOW - days * DAY - seconds_before)


def _key(days: int) -> str:
    return f"slack-day-C001-{datetime.fromtimestamp(NOW - days * DAY - 60, UTC).date().isoformat()}"


def _evidence(days: int, seconds_before: int, quote: str, role: str = "supports") -> dict:
    return {"locator": f"slack:C001/{_ts(days, seconds_before)}", "quote": quote, "role": role}


def _record(ref: str, kind: str, title: str, evidence: list, **extra) -> dict:
    lifecycle = extra.pop("lifecycle", "open")
    base = {"ref": ref, "match": {"decision": "new"}, "kind": kind, "title": title, "lifecycle": lifecycle,
            "basis": "stated", "evidence": evidence}
    if kind == "decision":
        base["reasoning"] = "agreed in the thread"
    return base | extra


def _write(folder, days: int, calls: list[list[dict]]) -> None:
    (folder / f"{_key(days)}.json").write_text(json.dumps({"calls": [{"result": {"records": r}} for r in calls]}))


def build(target):
    f.write_slack_workspace(target, URL, USERS, CONVERSATIONS)
    t28 = [f.slack_message("U001", "Someone should review the vendor contract", _ts(28, 3600)),
           f.slack_message("U001", "Which region first?", _ts(28, 1800)),
           f.slack_message("U001", "We use Postgres", _ts(28, 60))]
    t20 = [f.slack_message("U001", "Dana will ship the report", _ts(20, 3600)),
           f.slack_message("U001", "The report shipped", _ts(20, 60))]
    t12 = [f.slack_message("U001", "I will file the taxes", _ts(12, 60))]
    t10 = [f.slack_message("U001", "Launch on Dec 1", _ts(10, 3600)), f.slack_message("U001", "Launch on Dec 8", _ts(10, 60))]
    t3 = [f.slack_message("U001", "I will send the invoice", _ts(3, 60))]
    first = [*t28,*t20, *t12, *t10, *t3]
    f.write_slack_history(target, "C001", first)
    edited = [*first[:-1], f.slack_message("U001", "I will send the invoice soon", _ts(3, 60))]
    f.write_slack_history(target, "C001", edited, generation=1)

    folder = target / "extraction"
    folder.mkdir()
    _write(folder, 28, [
        [_record("a", "action_item", VENDOR, [_evidence(28, 3600, "review the vendor contract")], commitment="request"),
         _record("q", "open_question", REGION, [_evidence(28, 1800, "Which region first?")]),
         _record("d", "decision", POSTGRES, [_evidence(28, 60, "We use Postgres")], lifecycle="done")],
    ])
    _write(folder, 20, [[_record("a", "action_item", SHIP, [
        _evidence(20, 3600, "Dana will ship the report"), _evidence(20, 60, "The report shipped", "completes")],
        commitment="commitment", lifecycle="done")]])
    _write(folder, 12, [[_record("a", "action_item", TAXES, [_evidence(12, 60, "I will file the taxes")],
                                 commitment="intention", lifecycle="done")]])
    _write(folder, 10, [[
        _record("x", "decision", DEC1, [_evidence(10, 3600, "Launch on Dec 1")], links=[{"type": "contradicts", "to": {"ref": "y"}}]),
        _record("y", "decision", DEC8, [_evidence(10, 60, "Launch on Dec 8")]),
    ]])
    _write(folder, 3, [
        [_record("a", "action_item", INVOICE, [_evidence(3, 60, "I will send the invoice")], commitment="intention")],
        [],
    ])
