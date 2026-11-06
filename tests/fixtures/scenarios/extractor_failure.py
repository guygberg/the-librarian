"""One picked channel: a thread whose extraction fails, and two loose messages that extract cleanly.

Import with LIBRARIAN_NOW=NOW. Unit keys: THREAD_KEY fails, DAY_KEY succeeds.
"""

import json

from fixtures import formats as f

NOW = 1_700_000_000
DAY = 86_400
URL = "https://acme-test.slack.com/"
USERS = [{"id": "U001", "name": "dana", "real_name": "Dana Levi"}]
CONVERSATIONS = [{"id": "C001", "name": "atlas-dev", "is_channel": True, "is_private": False, "num_members": 12}]

ROOT_TS = f.ts(NOW - DAY)
LOOSE_TS = [f.ts(NOW - 2 * DAY + n) for n in (10, 20)]
THREAD_KEY = f"slack-thread-C001-{ROOT_TS}"
DAY_KEY = "slack-day-C001-2023-11-12"
BROKEN = "model crashed on the thread"


def day_result() -> dict:
    return {
        "records": [
            {
                "ref": "a1",
                "match": {"decision": "new"},
                "kind": "open_question",
                "title": "Where is the second loose message from?",
                "lifecycle": "open",
                "basis": "stated",
                "evidence": [{"locator": f"slack:C001/{LOOSE_TS[1]}", "quote": "loose two", "role": "supports"}],
            }
        ]
    }


def build(target):
    f.write_slack_workspace(target, URL, USERS, CONVERSATIONS)
    root = f.slack_message("U001", "thread root", ROOT_TS, thread_ts=ROOT_TS)
    reply = f.slack_message("U001", "thread reply", f.ts(NOW - DAY + 30), thread_ts=ROOT_TS)
    loose = [f.slack_message("U001", text, ts) for text, ts in zip(("loose one", "loose two"), LOOSE_TS, strict=True)]
    f.write_slack_history(target, "C001", [*loose, {**root, "reply_count": 1}])
    f.write_slack_replies(target, "C001", ROOT_TS, [root, reply])
    folder = target / "extraction"
    folder.mkdir()
    (folder / f"{THREAD_KEY}.json").write_text(json.dumps({"error": BROKEN}))
    (folder / f"{DAY_KEY}.json").write_text(json.dumps({"result": day_result()}))
