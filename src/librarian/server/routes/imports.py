"""The import panel: start and watch an Import, dry-run it, the Slack picked list, and older Slack history."""

from urllib.parse import parse_qs

from librarian import config, engines, paths
from librarian.cli import Context
from librarian.commands import import_
from librarian.importer import slack_fetch
from librarian.importer.lock import LockHeld
from librarian.link import review_actions as actions
from librarian.server import jobs
from librarian.server.routes import Route
from librarian.server.routes.review import _field
from librarian.slack import picks

PICKED_NOTE = "Only picked conversations are fetched and sent to Claude."


def _progress(req):
    with req.ro() as conn:
        return jobs.snapshot(conn, req.workspace, config.load())


def _refused(req):
    return 409, {"error": "an import is already running", **_progress(req)}


def get_import(req):
    return 200, _progress(req)


def start(req):
    if not jobs.start(req.workspace):
        return _refused(req)
    return 202, _progress(req)


def dry_run(req):
    ctx = Context(req.workspace, paths.data_home(), paths.workspace_dir(req.workspace), config.load())
    try:
        calls, failed = import_.count_calls(ctx)
    except LockHeld:
        return _refused(req)
    return 200, {"calls": calls, "failed": failed, "sent": 0}


def _picks(req, conn):
    picks.seed_once(conn, req.workspace, paths.workspace_dir(req.workspace))
    conversations = engines.get_engines(req.workspace).slack.list_conversations()
    return picks.rows(conversations, picks.picked_ids(conn, req.workspace))


def get_picks(req):
    with req.rw() as conn:
        return 200, {"conversations": _picks(req, conn), "note": PICKED_NOTE}


def post_picks(req):
    body = req.body if isinstance(req.body, dict) else {}
    lists = {key: body.get(key, []) for key in ("pick", "unpick")}
    if not all(isinstance(v, list) and all(isinstance(i, str) for i in v) for v in lists.values()):
        return 400, {"error": "pick and unpick must be lists of conversation ids"}
    with req.rw() as conn:
        picks.seed_once(conn, req.workspace, paths.workspace_dir(req.workspace))
        picks.edit_picks(conn, req.workspace, **lists)
        return 200, {"conversations": _picks(req, conn), "note": PICKED_NOTE}


def _older_row(req, conversation):
    with req.rw() as conn:
        match = [r for r in _picks(req, conn) if r["picked"] and conversation in (r["id"], r["name"])]
    return match[0] if match else None


def get_older(req):
    conversation = parse_qs(req.query).get("conversation", [""])[0]
    row = _older_row(req, conversation)
    if not row:
        return 404, {"error": f"{conversation!r} is not a picked conversation"}
    count = slack_fetch.count_older(engines.get_engines(req.workspace).slack, row["id"])
    return 200, {"conversation": row["name"], "count": count}


def post_older(req):
    try:
        conversation = _field(req.body, "conversation", str)
    except actions.Invalid as invalid:
        return invalid.status, {"error": invalid.message}
    if req.body.get("confirm") is not True:
        return 400, {"error": "confirm must be true; check the count from GET first"}
    row = _older_row(req, conversation)
    if not row:
        return 404, {"error": f"{conversation!r} is not a picked conversation"}
    if not jobs.start(req.workspace, "--older", row["id"]):
        return _refused(req)
    return 202, _progress(req)


ROUTES = [
    Route("GET", "/api/import", get_import),
    Route("POST", "/api/import/start", start),
    Route("POST", "/api/import/dry-run", dry_run),
    Route("GET", "/api/slack/picks", get_picks),
    Route("POST", "/api/slack/picks", post_picks),
    Route("GET", "/api/slack/import-older", get_older),
    Route("POST", "/api/slack/import-older", post_older),
]
