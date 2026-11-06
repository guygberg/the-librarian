"""A project that exists only in Slack: no recording, no session mentions it.

Import with LIBRARIAN_NOW=NOW. Canned extraction: DAY_KEY gives the project "Helios" and one
action that belongs to it.
"""

import json

from fixtures import formats as f

NOW = 1_700_000_000
DAY = 86_400
URL = "https://acme-test.slack.com/"
USERS = [{"id": "U001", "name": "dana", "real_name": "Dana Levi"}]
CONVERSATIONS = [
    {"id": "C001", "name": "helios", "is_channel": True, "is_private": False, "num_members": 5}
]
DAY_KEY = "slack-day-C001-2023-11-12"
PROJECT, ACTION = "Helios", "Draft the Helios plan"
TEXT = "Helios kicks off next week, I will draft the plan"
TS = f.ts(NOW - 2 * DAY)


def build(target):
    f.write_slack_workspace(target, URL, USERS, CONVERSATIONS)
    f.write_slack_history(target, "C001", [f.slack_message("U001", TEXT, TS)])
    evidence = [{"locator": f"slack:C001/{TS}", "quote": TEXT, "role": "supports"}]
    base = {
        "match": {"decision": "new"},
        "lifecycle": "open",
        "basis": "stated",
        "evidence": evidence,
    }
    records = [
        {**base, "ref": "p", "kind": "project", "title": PROJECT},
        {
            **base,
            "ref": "a",
            "kind": "action_item",
            "title": ACTION,
            "commitment": "intention",
            "links": [{"type": "belongs_to", "to": {"ref": "p"}}],
        },
    ]
    folder = target / "extraction"
    folder.mkdir()
    (folder / f"{DAY_KEY}.json").write_text(json.dumps({"result": {"records": records}}))
