"""The "last visit" marker: when the person last dismissed the what-changed strip, kept in the Workspace data."""

import json

from librarian import paths
from librarian.clock import utc_now_iso
from librarian.server.routes import Route

MARKER = "last_visit.json"


def _file(req):
    return paths.workspace_dir(req.workspace) / MARKER


def _last(req):
    try:
        return json.loads(_file(req).read_text())["at"]
    except (OSError, ValueError, KeyError):
        return None


def get_visit(req):
    last = _last(req)
    with req.ro() as conn:
        changed = conn.execute(
            "SELECT count(*) FROM records WHERE workspace = ? AND updated_at > ?", (req.workspace, last or "")
        ).fetchone()[0]
    return 200, {"last_visit": last, "changed": changed}


def post_seen(req):
    path = _file(req)
    path.parent.mkdir(parents=True, exist_ok=True)
    # The wall clock, because that is what stamps `records.updated_at` (not the LIBRARIAN_NOW test clock).
    path.write_text(json.dumps({"at": utc_now_iso()}))
    return 200, {"last_visit": json.loads(path.read_text())["at"]}


ROUTES = [Route("GET", "/api/visit", get_visit), Route("POST", "/api/visit/seen", post_seen)]
