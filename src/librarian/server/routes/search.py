from urllib.parse import parse_qs

from librarian.query import search
from librarian.server.routes import Route


def get(req):
    params = parse_qs(req.query)
    if not params.get("q"):
        return 400, {"error": {"code": "bad_request", "message": "q is required"}}
    with req.ro() as conn:
        return 200, search.search(conn, req.workspace, params["q"][0])


ROUTES = [Route("GET", "/api/search", get)]
