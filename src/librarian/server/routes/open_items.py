from librarian.query import open_items
from librarian.server.routes import Route


def get(req):
    with req.ro() as conn:
        return 200, open_items.open_items(conn, req.workspace)


ROUTES = [Route("GET", "/api/open-items", get)]
