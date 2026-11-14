"""Accept or reject a stored Suggestion. The answer is the settled Suggestion and, when a Record
was made or touched, its new current view."""

from librarian import config
from librarian.link import suggestion_actions as actions
from librarian.link.errors import Invalid
from librarian.query import core
from librarian.server.routes import Route


def _settle(do):
    def handler(req):
        try:
            suggestion_id = int(req.params["id"])
        except ValueError:
            return 400, {"error": "bad Suggestion id"}
        with req.rw() as conn:
            try:
                result = do(conn, req.workspace, suggestion_id)
            except Invalid as refused:
                return refused.status, {"error": refused.message}
            if result["record_id"] is not None:
                result["record"] = core.current_view(
                    conn, req.workspace, result["record_id"], config.load()
                )
            return 200, result

    return handler


ROUTES = [
    Route("POST", "/api/suggestions/<id>/accept", _settle(actions.accept)),
    Route("POST", "/api/suggestions/<id>/reject", _settle(actions.reject)),
]
