"""Set the speaker of a transcript segment: `POST /api/speaker {locator, person_id | name}`."""

from librarian import config
from librarian.link import speaker
from librarian.query import core
from librarian.server.routes import Refused, Route, field


def post(req):
    with req.rw() as conn:
        try:
            person = field(req.body, "person_id", int, required=False) or field(req.body, "name", str)
            changed = speaker.set_speaker(conn, req.workspace, field(req.body, "locator", str), person)
        except Refused as invalid:
            return invalid.status, {"error": invalid.message}
        return 200, {"records": [core.current_view(conn, req.workspace, rid, config.load()) for rid in changed]}


ROUTES = [Route("POST", "/api/speaker", post)]
