from urllib.parse import parse_qs

from librarian.query import project
from librarian.server.routes import Route


def get(req):
    names = parse_qs(req.query).get("name")
    if not names:
        return 400, {"error": {"code": "bad_request", "message": "name is required"}}
    with req.ro() as conn:
        return 200, project.project(conn, req.workspace, names[0])


ROUTES = [Route("GET", "/api/project", get)]
