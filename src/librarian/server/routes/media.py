import json
import mimetypes

from librarian.importer import recordings
from librarian.server.routes import File, Route


def get(req):
    """The recording file behind a transcript, found through its first segment. Only files under the Drive folder."""
    root = recordings.drive_dir()
    with req.ro() as conn:
        row = conn.execute(
            "SELECT r.content FROM source_items i JOIN source_item_revisions r ON r.source_item_id = i.id"
            " WHERE i.workspace = ? AND i.source = ? AND i.stable_id = ? ORDER BY r.revision DESC LIMIT 1",
            (req.workspace, recordings.SEGMENT_SOURCE, f"{req.params['file_id']}/1"),
        ).fetchone()
    path = (root / json.loads(row[0])["path"]).resolve() if row and root else None
    if path is None or not path.is_relative_to(root.resolve()) or not path.is_file():
        return 404, {"error": "no such recording"}
    return 200, File(path, mimetypes.guess_type(path.name)[0] or "application/octet-stream")


ROUTES = [Route("GET", "/media/drive/<file_id>", get, media=True)]
