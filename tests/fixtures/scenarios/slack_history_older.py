"""One picked-able channel whose history reaches back past the 30-day window.

Import with LIBRARIAN_NOW=NOW. Holds old messages, recent ones and a thread with replies.
"""

from fixtures import formats as f

NOW = 1_700_000_000
DAY = 86_400
URL = "https://acme-test.slack.com/"
USERS = [{"id": "U001", "name": "dana", "real_name": "Dana Levi"}]
CONVERSATIONS = [
    {"id": "C001", "name": "atlas-dev", "is_channel": True, "is_private": False, "num_members": 12},
    {"id": "C002", "name": "random", "is_channel": True, "is_private": False, "num_members": 30},
]


def messages():
    old = [f.slack_message("U001", f"old {n}", f.ts(NOW - 40 * DAY + n)) for n in range(3)]
    recent = [f.slack_message("U001", f"recent {n}", f.ts(NOW - 10 * DAY + n)) for n in range(3)]
    parent_ts = f.ts(NOW - 5 * DAY)
    parent = {**f.slack_message("U001", "thread parent", parent_ts, parent_ts), "reply_count": 2}
    return old + recent + [parent], parent_ts


def build(target):
    f.write_slack_workspace(target, URL, USERS, CONVERSATIONS)
    history, parent_ts = messages()
    f.write_slack_history(target, "C001", history)
    replies = [
        f.slack_message("U001", f"reply {n}", f.ts(NOW - 5 * DAY + n + 1), parent_ts)
        for n in range(2)
    ]
    f.write_slack_replies(target, "C001", parent_ts, [history[-1], *replies])
    f.write_slack_history(target, "C002", [f.slack_message("U001", "not picked", f.ts(NOW - DAY))])
