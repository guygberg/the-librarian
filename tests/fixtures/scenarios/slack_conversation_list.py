"""Replayed Slack conversation list: one conversation of each kind, no history pages."""

from fixtures import formats as f

USERS = [{"id": "U001", "name": "dana", "real_name": "Dana Levi"}]

CONVERSATIONS = [
    {"id": "C001", "name": "atlas-dev", "is_channel": True, "is_private": False, "num_members": 12},
    {"id": "G001", "name": "atlas-leads", "is_group": True, "is_private": True, "num_members": 4},
    {"id": "D001", "is_im": True, "is_private": True, "user": "U001", "num_members": 2},
    {"id": "M001", "name": "mpdm-dana--omer-1", "is_mpim": True, "is_private": True, "num_members": 3},
]


def build(target):
    f.write_slack_workspace(target, "https://acme-test.slack.com/", USERS, CONVERSATIONS)
