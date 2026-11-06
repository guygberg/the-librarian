"""People for the link stage: a Slack login ("Omer Katz" is Me), two users whose names
collide, a Hebrew me-name, a near-duplicate name, and a recording with a first-person line.

Import with LIBRARIAN_NOW=NOW and the config `me_names` ME_NAMES. Canned extraction:
DAY_KEY (Slack), RECORDING_KEY.
"""

import json
import random

from fixtures import formats as f
from librarian.importer import recordings

NOW = 1_700_000_000
DAY = 86_400
URL = "https://acme-test.slack.com/"
USERS = [
    {"id": "U001", "name": "omer", "real_name": "Omer Katz"},
    {"id": "U002", "name": "dcohen", "real_name": "Dana Cohen"},
    {"id": "U003", "name": "dana.c", "real_name": "dana  cohen"},
]
CONVERSATIONS = [
    {"id": "C001", "name": "atlas-dev", "is_channel": True, "is_private": False, "num_members": 12}
]
ME_NAMES = ["Omer K", "עומר כץ"]
DAY_KEY = "slack-day-C001-2023-11-12"
RECORDING = "Sync - 2026-10-12 10.00 GMT+03.00 - Recording"
FIRST_PERSON = "I will send the report"
# (title, owner, message text); the title is the Record's, one Record per message
OWNERS = [
    ("By id", {"slack_user": "U002"}, "message one"),
    ("By id, not in the users list", {"slack_user": "U099"}, "message two"),
    ("By colliding name", {"name": "Dana Cohen"}, "message three"),
    ("By near-duplicate name", {"name": "Dana Cohn"}, "message four"),
    ("By Hebrew me-name", {"name": "עומר כץ"}, "message five"),
    ("By login name", {"name": "omer katz"}, "message six"),
]


def _tss() -> list[str]:
    return [f.ts(NOW - 2 * DAY + 10 * n) for n in range(1, len(OWNERS) + 1)]


def _action(title: str, owner: dict, locator: str, quote: str) -> dict:
    return {
        "ref": title,
        "match": {"decision": "new"},
        "kind": "action_item",
        "title": title,
        "lifecycle": "open",
        "basis": "stated",
        "commitment": "request",
        "owner": owner,
        "evidence": [{"locator": locator, "quote": quote, "role": "supports"}],
    }


def build(target):
    f.write_slack_workspace(target, URL, USERS, CONVERSATIONS)
    stamps = _tss()
    f.write_slack_history(
        target,
        "C001",
        [
            f.slack_message("U001", text, ts)
            for (_, _, text), ts in zip(OWNERS, stamps, strict=True)
        ],
    )

    flat = target / "Meet Recordings"
    f.write_recording(flat, RECORDING, [f.segment(0.0, 3.0, FIRST_PERSON, random.Random(7))])
    key = f"drive-{recordings._file_hash(flat / RECORDING)[: recordings._ID_LENGTH]}-1"
    locator = f"drive:{recordings._file_hash(flat / RECORDING)[: recordings._ID_LENGTH]}/1"

    folder = target / "extraction"
    folder.mkdir()
    day = [
        _action(title, owner, f"slack:C001/{ts}", text)
        for (title, owner, text), ts in zip(OWNERS, stamps, strict=True)
    ]
    (folder / f"{DAY_KEY}.json").write_text(
        json.dumps({"result": {"records": day}}, ensure_ascii=False)
    )
    spoken = [_action("By first person", {"speaker": "first_person"}, locator, FIRST_PERSON)]
    (folder / f"{key}.json").write_text(json.dumps({"result": {"records": spoken}}))
