"""Record actions: each appends Person events and answers with the Record's new current view. No source is touched."""

from librarian import config, events
from librarian.query import core
from librarian.server.routes import Route

WRONG = "marked wrong by me"
_NOT_FOR_PROJECTS = "not available for a project"


class Refused(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


def _kind(conn, workspace, record_id):
    row = conn.execute("SELECT kind FROM records WHERE workspace = ? AND id = ?", (workspace, record_id)).fetchone()
    return row[0] if row else None


def _need_item(conn, workspace, record_id) -> None:
    kind = _kind(conn, workspace, int(record_id))
    if kind is None:
        raise Refused(404, f"no Record {record_id}")
    if kind == "project":
        raise Refused(409, _NOT_FOR_PROJECTS)


def _int(body, key) -> int:
    value = body.get(key) if isinstance(body, dict) else None
    if not isinstance(value, int) or isinstance(value, bool):
        raise Refused(400, f"{key} must be an integer")
    return value


def _lifecycle(lifecycle):
    def act(conn, workspace, record_id, body):
        events.append(conn, workspace, record_id, "status_change", {"lifecycle": lifecycle})

    return act


def _owner(conn, workspace, record_id, body):
    if _kind(conn, workspace, record_id) != "action_item":
        raise Refused(409, "only an action item has an owner")
    person_id = _int(body, "person_id")
    if not conn.execute("SELECT 1 FROM persons WHERE workspace = ? AND id = ?", (workspace, person_id)).fetchone():
        raise Refused(404, f"no person {person_id}")
    events.append(conn, workspace, record_id, "owner_change", {"person_id": person_id})


def _project(conn, workspace, record_id, body):
    project_id = _int(body, "project_id")
    if _kind(conn, workspace, project_id) != "project":
        raise Refused(404, f"no project {project_id}")
    events.append(conn, workspace, record_id, "project_move", {"project_id": project_id})


def _resolve(conn, workspace, record_id, body):
    """`other` is the Record it contradicts. `outcome`: `holds` (the other becomes superseded) or `both_wrong`."""
    other = _int(body, "other")
    outcome = body.get("outcome")
    if outcome not in ("holds", "both_wrong"):
        raise Refused(400, "outcome must be holds or both_wrong")
    _need_item(conn, workspace, other)
    linked = conn.execute(
        "SELECT 1 FROM links WHERE workspace = ? AND type = 'contradicts' AND from_type = 'record'"
        " AND to_type = 'record' AND ? IN (from_id, to_id) AND ? IN (from_id, to_id)",
        (workspace, record_id, other),
    ).fetchone()
    if not linked:
        raise Refused(409, f"Record {record_id} does not contradict Record {other}")
    if outcome == "holds":
        events.append(conn, workspace, record_id, "resolve_disagreement", {"with": other, "holds": True})
        events.append(conn, workspace, other, "resolve_disagreement", {"with": record_id, "lifecycle": "superseded"})
    else:
        for rid, rival in ((record_id, other), (other, record_id)):
            events.append(
                conn, workspace, rid, "resolve_disagreement", {"with": rival, "lifecycle": "dropped", "reason": WRONG}
            )


ACTIONS = {
    "done": _lifecycle("done"),
    "reopen": _lifecycle("open"),
    "owner": _owner,
    "project": _project,
    "resolve": _resolve,
}


def act(name):
    def handler(req):
        record_id = int(req.params["id"])
        with req.rw() as conn:
            try:
                _need_item(conn, req.workspace, record_id)
                ACTIONS[name](conn, req.workspace, record_id, req.body)
            except Refused as refused:
                return refused.status, {"error": refused.message}
            return 200, core.current_view(conn, req.workspace, record_id, config.load())

    return handler


ROUTES = [Route("POST", f"/api/records/<id>/{name}", act(name)) for name in ACTIONS]
