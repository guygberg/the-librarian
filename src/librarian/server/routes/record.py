from urllib.parse import parse_qs

from librarian import config
from librarian.query import core
from librarian.server.routes import Route


def get(req):
    """One Record's current view, with the Evidence of it and of every Record it disagrees with."""
    raw = req.params.get("id") or parse_qs(req.query).get("id", [""])[0]
    if not raw.isdigit():
        return 400, {"error": {"code": "bad_request", "message": "id must be a Record id"}}
    with req.ro() as conn:
        cfg = config.load()
        record = core.current_view(conn, req.workspace, int(raw), cfg)
        if record:
            record["subitems"] = [
                core.current_view(conn, req.workspace, child, cfg)
                for (child,) in conn.execute(
                    "SELECT id FROM items WHERE workspace = ? AND parent_id = ?"
                    " AND id NOT IN (SELECT item_id FROM tags) ORDER BY id",
                    (req.workspace, int(raw)),
                )
            ]
    if record is None:
        return 404, {"error": {"code": "not_found", "message": f"no Record {raw}"}}
    return 200, {"item": record} if req.params.get("id") else {"record": record}


ROUTES = [Route("GET", "/api/record", get), Route("GET", "/api/items/<id>", get)]
