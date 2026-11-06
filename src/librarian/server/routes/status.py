from librarian.server.routes import Route


def status(req):
    with req.ro() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    return 200, {"workspace": req.workspace, "schema_version": version}


ROUTES = [Route("GET", "/api/status", status)]
