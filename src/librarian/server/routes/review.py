"""The Review list and Alias corrections. Each action answers with the changed Record's new current view."""

from librarian import config
from librarian.link import review_actions as actions
from librarian.query import core
from librarian.server.routes import Route


def _field(body, key, kind, required=True):
    value = body.get(key) if isinstance(body, dict) else None
    if value is None and not required:
        return None
    if not isinstance(value, kind) or isinstance(value, bool) or value == "":
        raise actions.Invalid(400, f"{key} must be {'an integer' if kind is int else 'a non-empty string'}")
    return value


def get_review(req):
    with req.ro() as conn:
        return 200, actions.rows(conn, req.workspace)


def _act(do):
    def handler(req):
        with req.rw() as conn:
            try:
                record_id = do(conn, req.workspace, req)
            except actions.Invalid as invalid:
                return invalid.status, {"error": invalid.message}
            return 200, core.current_view(conn, req.workspace, record_id, config.load())

    return handler


def _accept(conn, workspace, req):
    return actions.accept(conn, workspace, int(req.params["id"]), _field(req.body, "person_id", int, required=False))


def _reject(conn, workspace, req):
    return actions.reject(conn, workspace, int(req.params["id"]))


def _move(conn, workspace, req):
    body = req.body
    record_id = _field(body, "record_id", int)
    actions.move_alias(
        conn, workspace, _field(body, "alias", str), _field(body, "from_person_id", int),
        _field(body, "to_person_id", int), record_id,
    )
    return record_id


def _split(conn, workspace, req):
    body = req.body
    record_id = _field(body, "record_id", int)
    actions.split_alias(
        conn, workspace, _field(body, "alias", str), _field(body, "from_person_id", int), record_id,
        _field(body, "name", str, required=False),
    )
    return record_id


ROUTES = [
    Route("GET", "/api/review", get_review),
    Route("POST", "/api/review/<id>/accept", _act(_accept)),
    Route("POST", "/api/review/<id>/reject", _act(_reject)),
    Route("POST", "/api/aliases/move", _act(_move)),
    Route("POST", "/api/aliases/split", _act(_split)),
]
