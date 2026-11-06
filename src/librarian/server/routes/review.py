"""The Review list and Alias corrections.

Each action answers with the changed Record's new current view.
"""

from librarian.link import review_actions as actions
from librarian.server.routes import Route, field, mutating


def get_review(req):
    with req.ro() as conn:
        return 200, actions.rows(conn, req.workspace)


def _accept(conn, workspace, req):
    return actions.accept(
        conn, workspace, int(req.params["id"]), field(req.body, "person_id", int, required=False)
    )


def _reject(conn, workspace, req):
    return actions.reject(conn, workspace, int(req.params["id"]))


def _move(conn, workspace, req):
    body = req.body
    record_id = field(body, "record_id", int)
    actions.move_alias(
        conn,
        workspace,
        field(body, "alias", str),
        field(body, "from_person_id", int),
        field(body, "to_person_id", int),
        record_id,
    )
    return record_id


def _split(conn, workspace, req):
    body = req.body
    record_id = field(body, "record_id", int)
    actions.split_alias(
        conn,
        workspace,
        field(body, "alias", str),
        field(body, "from_person_id", int),
        record_id,
        field(body, "name", str, required=False),
    )
    return record_id


ROUTES = [
    Route("GET", "/api/review", get_review),
    Route("POST", "/api/review/<id>/accept", mutating(_accept)),
    Route("POST", "/api/review/<id>/reject", mutating(_reject)),
    Route("POST", "/api/aliases/move", mutating(_move)),
    Route("POST", "/api/aliases/split", mutating(_split)),
]
