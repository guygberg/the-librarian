"""Project corrections from the status header. Each answers with the resulting project's current view.
Moving a Record is `POST /api/records/<id>/project`."""

from librarian import config
from librarian.link import project_actions as actions
from librarian.query import core
from librarian.server.routes import Route
from librarian.server.routes.review import _field


def _list(body, key):
    value = body.get(key) if isinstance(body, dict) else None
    if not isinstance(value, list) or not all(isinstance(v, int) and not isinstance(v, bool) for v in value):
        raise actions.Invalid(400, f"{key} must be a list of integers")
    return value


def _act(do):
    def handler(req):
        with req.rw() as conn:
            try:
                project_id = do(conn, req.workspace, int(req.params["id"]), req.body)
            except actions.Invalid as invalid:
                return invalid.status, {"error": invalid.message}
            return 200, core.current_view(conn, req.workspace, project_id, config.load())

    return handler


def _confirm(conn, workspace, project_id, body):
    return actions.confirm(conn, workspace, project_id)


def _rename(conn, workspace, project_id, body):
    return actions.rename(conn, workspace, project_id, _field(body, "name", str))


def _merge(conn, workspace, project_id, body):
    return actions.merge(conn, workspace, project_id, _field(body, "into", int))


def _split(conn, workspace, project_id, body):
    return actions.split(conn, workspace, project_id, _field(body, "name", str), _list(body, "record_ids"))


ROUTES = [
    Route("POST", f"/api/projects/<id>/{name}", _act(do))
    for name, do in (("confirm", _confirm), ("rename", _rename), ("merge", _merge), ("split", _split))
]
