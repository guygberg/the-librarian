from urllib.parse import parse_qs

from librarian.query import context
from librarian.server.routes import Route


def get(req):
    params = parse_qs(req.query)
    if not params.get("locator"):
        return 400, {"error": {"code": "bad_request", "message": "locator is required"}}
    with req.ro() as conn:
        return context.answer(conn, req.workspace, params["locator"][0])


ROUTES = [Route("GET", "/api/context", get)]
