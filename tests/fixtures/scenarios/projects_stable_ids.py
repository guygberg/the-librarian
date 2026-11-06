"""Projects across Imports: one Slack channel, one message per day, replayed with an edit
and a new message.

Import with LIBRARIAN_NOW=NOW. Canned extraction (the Nth call for a unit gets the Nth entry):
- DAY1: project "Atlas Migration" and an action; the second call (after the edit) says
  same / updated.
- DAY2: project "Atlas Migrations" (a near name) and an action that belongs to it.
- DAY3 (only from the second Import): project "Helios" and an action that belongs to it.
Record ids follow the newest-first extraction order: Atlas Migration 1, its action 2,
Atlas Migrations 3, its action 4.
"""

import json
from datetime import UTC, datetime

from fixtures import formats as f

NOW = 1_700_000_000
DAY = 86_400
URL = "https://acme-test.slack.com/"
USERS = [{"id": "U001", "name": "dana", "real_name": "Dana Levi"}]
CONVERSATIONS = [
    {"id": "C001", "name": "atlas-dev", "is_channel": True, "is_private": False, "num_members": 12}
]

TS = {1: f.ts(NOW - 1 * DAY), 2: f.ts(NOW - 2 * DAY), 3: f.ts(NOW - 3 * DAY)}
KEYS = {
    n: f"slack-day-C001-{datetime.fromtimestamp(float(ts), UTC).date().isoformat()}"
    for n, ts in TS.items()
}
TEXT1 = "Atlas Migration kickoff: Dana drafts the plan"
TEXT1_EDITED = TEXT1 + " by Friday"
TEXT2 = "Atlas Migrations rollout: Lee writes the notes"
TEXT3 = "Helios launch: Sam books the venue"


def _project(title: str, locator: str, quote: str, **match) -> dict:
    return {
        "ref": "p",
        "match": match or {"decision": "new"},
        "kind": "project",
        "title": title,
        "lifecycle": "open",
        "basis": "stated",
        "evidence": [{"locator": locator, "quote": quote, "role": "supports"}],
    }


def _action(title: str, locator: str, quote: str, links=None, **extra) -> dict:
    return {
        "ref": "a",
        "match": {"decision": "new"},
        "kind": "action_item",
        "title": title,
        "lifecycle": "open",
        "basis": "stated",
        "commitment": "request",
        "links": links or [{"type": "belongs_to", "to": {"ref": "p"}}],
        "evidence": [{"locator": locator, "quote": quote, "role": "supports"}],
        **extra,
    }


def _write(folder, key, calls):
    (folder / f"{key}.json").write_text(
        json.dumps({"calls": [{"result": {"records": r}} for r in calls]})
    )


def build(target):
    f.write_slack_workspace(target, URL, USERS, CONVERSATIONS)
    first = [f.slack_message("U001", TEXT1, TS[1]), f.slack_message("U001", TEXT2, TS[2])]
    f.write_slack_history(target, "C001", first)
    second = [
        f.slack_message("U001", TEXT1_EDITED, TS[1]),
        first[1],
        f.slack_message("U001", TEXT3, TS[3]),
    ]
    f.write_slack_history(target, "C001", second, generation=1)

    loc = {n: f"slack:C001/{ts}" for n, ts in TS.items()}
    folder = target / "extraction"
    folder.mkdir()
    _write(
        folder,
        KEYS[1],
        [
            [
                _project("Atlas Migration", loc[1], "Atlas Migration kickoff"),
                _action("Draft the plan", loc[1], "Dana drafts the plan"),
            ],
            [
                _project(
                    "Atlas Migration", loc[1], "Atlas Migration kickoff", decision="same", id=1
                ),
                _action(
                    "Draft the plan",
                    loc[1],
                    "drafts the plan by Friday",
                    stated_deadline="2023-11-17",
                )
                | {"match": {"decision": "updated", "id": 2}},
            ],
        ],
    )
    _write(
        folder,
        KEYS[2],
        [
            [
                _project("Atlas Migrations", loc[2], "Atlas Migrations rollout"),
                _action("Write the notes", loc[2], "Lee writes the notes"),
            ]
        ],
    )
    _write(
        folder,
        KEYS[3],
        [
            [
                _project("Helios", loc[3], "Helios launch"),
                _action("Book the venue", loc[3], "Sam books the venue"),
            ]
        ],
    )
