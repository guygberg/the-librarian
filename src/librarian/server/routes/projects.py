"""Project corrections from the status header. Each answers with the resulting project's current view.
Moving a Record is `POST /api/records/<id>/project`."""

from librarian.link import project_actions as actions
from librarian.server.routes import Route, field, mutating


def _project_id(req) -> int:
    return int(req.params["id"])


def _confirm(conn, workspace, req):
    return actions.confirm(conn, workspace, _project_id(req))


def _rename(conn, workspace, req):
    return actions.rename(conn, workspace, _project_id(req), field(req.body, "name", str))


def _merge(conn, workspace, req):
    return actions.merge(conn, workspace, _project_id(req), field(req.body, "into", int))


def _split(conn, workspace, req):
    return actions.split(conn, workspace, _project_id(req), field(req.body, "name", str), field(req.body, "record_ids", list))


ROUTES = [
    Route("POST", f"/api/projects/<id>/{name}", mutating(do))
    for name, do in (("confirm", _confirm), ("rename", _rename), ("merge", _merge), ("split", _split))
]
