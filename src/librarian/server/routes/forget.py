"""Forget a Slack conversation: `POST /api/forget {conversation, confirm: true}`."""

from librarian import forget, paths
from librarian.importer.lock import LockHeld, workspace_lock
from librarian.server.routes import Refused, Route, field


def post(req):
    try:
        conversation = field(req.body, "conversation", str)
    except Refused as invalid:
        return invalid.status, {"error": invalid.message}
    if req.body.get("confirm") is not True:
        return 400, {"error": "confirm must be true; forgetting deletes data"}
    try:
        with workspace_lock(paths.workspace_dir(req.workspace)), req.rw() as conn:
            if not (forget.items_of(conn, req.workspace, conversation)):
                return 404, {"error": f"no stored messages for conversation {conversation!r}"}
            return 200, forget.forget(conn, req.workspace, conversation)
    except LockHeld as held:
        return 409, {"error": f"an import is running ({held.holder})"}


ROUTES = [Route("POST", "/api/forget", post)]
