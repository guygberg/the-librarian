from urllib.parse import parse_qs

from librarian.query import open_items
from librarian.server.routes import Route


def get(req):
    everything = parse_qs(req.query).get("scope") == ["all"]
    with req.ro() as conn:
        return 200, open_items.open_items(conn, req.workspace, everything=everything)


ROUTES = [Route("GET", "/api/open-items", get)]
