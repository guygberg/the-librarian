"""Thin GET routes for the read-only answer commands that take an optional project or a topic."""

from urllib.parse import parse_qs

from librarian.query import blocked, changes, decision, waiting
from librarian.server.routes import Route


def _param(req, key):
    values = parse_qs(req.query).get(key)
    return values[0] if values else None


def get_changes(req):
    with req.ro() as conn:
        return 200, changes.changes(conn, req.workspace, _param(req, "project"))


def get_blocked(req):
    with req.ro() as conn:
        return 200, blocked.blocked(conn, req.workspace, _param(req, "project"))


def get_waiting(req):
    with req.ro() as conn:
        return 200, waiting.waiting(conn, req.workspace)


def get_decision(req):
    topic = _param(req, "topic")
    if not topic:
        return 400, {"error": {"code": "bad_request", "message": "topic is required"}}
    with req.ro() as conn:
        return 200, decision.decision(conn, req.workspace, topic)


ROUTES = [
    Route("GET", "/api/changes", get_changes),
    Route("GET", "/api/waiting", get_waiting),
    Route("GET", "/api/decision", get_decision),
    Route("GET", "/api/blocked", get_blocked),
]
