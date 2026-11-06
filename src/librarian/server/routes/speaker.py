"""Set the speaker of a transcript segment: `POST /api/speaker {locator, person_id}`."""

from librarian import config
from librarian.link import review_actions as actions
from librarian.link import speaker
from librarian.query import core
from librarian.server.routes import Route
from librarian.server.routes.review import _field


def post(req):
    with req.rw() as conn:
        try:
            changed = speaker.set_speaker(
                conn, req.workspace, _field(req.body, "locator", str), _field(req.body, "person_id", int)
            )
        except actions.Invalid as invalid:
            return invalid.status, {"error": invalid.message}
        return 200, {"records": [core.current_view(conn, req.workspace, rid, config.load()) for rid in changed]}


ROUTES = [Route("POST", "/api/speaker", post)]
