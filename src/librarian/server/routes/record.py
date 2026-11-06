from urllib.parse import parse_qs

from librarian import config
from librarian.query import core
from librarian.server.routes import Route


def get(req):
    """One Record's current view, with the Evidence of it and of every Record it disagrees with."""
    raw = parse_qs(req.query).get("id", [""])[0]
    if not raw.isdigit():
        return 400, {"error": {"code": "bad_request", "message": "id must be a Record id"}}
    with req.ro() as conn:
        record = core.current_view(conn, req.workspace, int(raw), config.load())
    if record is None:
        return 404, {"error": {"code": "not_found", "message": f"no Record {raw}"}}
    return 200, {"record": record}


ROUTES = [Route("GET", "/api/record", get)]
