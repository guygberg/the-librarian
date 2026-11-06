"""One channel of more than 200 messages and a thread of more than 200 replies, all inside
30 days."""

from fixtures import formats as f

NOW = 1_700_000_000
DAY = 86_400
MESSAGES = 450
REPLIES = 230
USERS = [{"id": "U001", "name": "dana", "real_name": "Dana Levi"}]
CONVERSATIONS = [
    {"id": "C001", "name": "atlas-dev", "is_channel": True, "is_private": False, "num_members": 12}
]


def build(target):
    f.write_slack_workspace(target, "https://acme-test.slack.com/", USERS, CONVERSATIONS)
    base = NOW - 20 * DAY
    thread_ts = f.ts(base - 1)
    top = [f.slack_message("U001", f"m{n}", f.ts(base + n)) for n in range(MESSAGES)]
    parent = {**f.slack_message("U001", "big thread", thread_ts, thread_ts), "reply_count": REPLIES}
    f.write_slack_history(target, "C001", [parent, *top])
    replies = [
        f.slack_message("U001", f"r{n}", f.ts(base - 1, n + 1), thread_ts) for n in range(REPLIES)
    ]
    f.write_slack_replies(target, "C001", thread_ts, [parent, *replies])
