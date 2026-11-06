from urllib.parse import parse_qs

from librarian.query import graph
from librarian.server.routes import Route


def _bad(message):
    return 400, {"error": {"code": "bad_request", "message": message}}


def get(req):
    params = parse_qs(req.query)
    try:
        center = graph.parse_center(params.get("center", [""])[0])
        hops = int(params.get("hops", ["1"])[0])
    except (graph.BadGraphRequest, ValueError) as err:
        return _bad(str(err))
    if not 1 <= hops <= graph.MAX_HOPS:
        return _bad(f"hops must be 1..{graph.MAX_HOPS}")
    kinds = tuple(k for k in params.get("kinds", [""])[0].split(",") if k) or graph.KINDS
    unknown = [k for k in kinds if k not in graph.KINDS]
    if unknown:
        return _bad(f"unknown edge kind {unknown[0]!r}")
    with req.ro() as conn:
        found = graph.neighbourhood(conn, req.workspace, center, hops, kinds)
    if found is None:
        return 404, {
            "error": {"code": "not_found", "message": f"no such node {params['center'][0]}"}
        }
    return 200, found


ROUTES = [Route("GET", "/api/graph", get)]
