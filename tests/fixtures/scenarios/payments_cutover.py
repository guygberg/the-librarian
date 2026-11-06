"""The Payments migration project across Slack and a recording (UI scenario `payments-cutover`).

Import with LIBRARIAN_NOW=NOW. Canned extraction: SLACK_KEY (the project, the Nov 18
decision, "Keep webhook v1", a blocker owned by Raz, and two items with no Evidence at all)
and RECORDING_KEY (the Nov 25 decision at 00:41:10, which contradicts the Nov 18 one). The
recording's Record cites a candidate by Record id, so it relies on the Slack unit being
stored first: the project is Record PROJECT_ID, the Nov 18 decision NOV_18_ID.
"""

import json
import random
from datetime import UTC, datetime

from fixtures import formats as f
from librarian.importer import recordings

NOW = 1_700_000_000
DAY = 86_400
URL = "https://acme-test.slack.com/"
USERS = [
    {"id": "U001", "name": "dana", "real_name": "Dana Levi"},
    {"id": "U002", "name": "raz", "real_name": "Raz Peretz"},
]
CONVERSATIONS = [
    {"id": "C001", "name": "payments", "is_channel": True, "is_private": False, "num_members": 8}
]
RECORDING = "Payments sync - 2023-11-13 10.00 GMT+02.00 - Recording"
CUTOVER_SPEECH = "Payments migration cutover: Nov 25 to be safe"
CUTOVER_START = 2470.0  # 00:41:10

PROJECT, NOV_18, NOV_25 = "Payments migration", "Cutover on Nov 18", "Cutover on Nov 25 to be safe"
WEBHOOK, BLOCKER = "Keep webhook v1", "Bank sandbox credentials missing"
UNCITED = ["Run a rollback drill in Q1", "Schedule the post-cutover review"]
PROJECT_ID, NOV_18_ID = 1, 2

_SLACK_AT = NOW - 3 * DAY
MESSAGES = [
    ("U001", "Payments migration: the cutover is Nov 18", f.ts(_SLACK_AT - 3600)),
    ("U002", "We keep webhook v1 until after the cutover", f.ts(_SLACK_AT - 1800)),
    ("U002", "Still blocked on the bank sandbox credentials", f.ts(_SLACK_AT - 60)),
]
SLACK_KEY = f"slack-day-C001-{datetime.fromtimestamp(_SLACK_AT, UTC).date().isoformat()}"


def _record(ref: str, kind: str, title: str, locator: str, quote: str, **extra) -> dict:
    base = {
        "ref": ref,
        "match": {"decision": "new"},
        "kind": kind,
        "title": title,
        "lifecycle": "open",
        "basis": "stated",
        "evidence": [{"locator": locator, "quote": quote, "role": "supports"}],
    }
    if kind == "decision":
        base["reasoning"] = "agreed in the thread"
    return base | extra


def _uncited(ref: str, title: str) -> dict:
    return _record(ref, "action_item", title, "", "") | {"evidence": [], "commitment": "intention"}


def build(target):
    f.write_slack_workspace(target, URL, USERS, CONVERSATIONS)
    f.write_slack_history(
        target, "C001", [f.slack_message(user, text, ts) for user, text, ts in MESSAGES]
    )

    flat = target / "Meet Recordings"
    f.write_recording(
        flat,
        RECORDING,
        [
            f.segment(0.0, 4.0, "Quick sync on the Payments migration", random.Random(7)),
            f.segment(CUTOVER_START, CUTOVER_START + 6, CUTOVER_SPEECH, random.Random(8)),
        ],
    )
    file_id = recordings._file_hash(flat / RECORDING)[: recordings._ID_LENGTH]

    belongs = [{"type": "belongs_to", "to": {"ref": "p"}}]
    slack = [f"slack:C001/{ts}" for _, _, ts in MESSAGES]
    day = [
        _record("p", "project", PROJECT, slack[0], "the cutover is Nov 18"),
        _record("d1", "decision", NOV_18, slack[0], "the cutover is Nov 18", links=belongs),
        _record("d2", "decision", WEBHOOK, slack[1], "We keep webhook v1", links=belongs),
        _record(
            "b",
            "blocker",
            BLOCKER,
            slack[2],
            "blocked on the bank sandbox credentials",
            links=[
                *belongs,
                {"type": "owner", "to": {"slack_user": "U002"}},
                {"type": "blocks", "to": {"ref": "p"}},
            ],
        ),
        _uncited("u1", UNCITED[0]),
        _uncited("u2", UNCITED[1]),
    ]
    spoken = [
        _record(
            "d3",
            "decision",
            NOV_25,
            f"drive:{file_id}/2",
            "Nov 25 to be safe",
            links=[
                {"type": "belongs_to", "to": {"id": PROJECT_ID}},
                {"type": "contradicts", "to": {"id": NOV_18_ID}},
            ],
        )
    ]
    folder = target / "extraction"
    folder.mkdir()
    (folder / f"{SLACK_KEY}.json").write_text(json.dumps({"result": {"records": day}}))
    (folder / f"drive-{file_id}-3.json").write_text(json.dumps({"result": {"records": spoken}}))
