import sqlite3

import pytest

from fixtures.scenarios import recording_uncertain_hebrew as hebrew
from support.recordings import make_env, run_import
from support.serve import spawn


@pytest.fixture
def media(tmp_path, home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    env, fixtures = make_env(tmp_path, home, "recording-uncertain-hebrew")
    code, out = run_import(home, env)
    assert code == 0, out
    db = sqlite3.connect(next(home.rglob("*.db")))
    file_id = db.execute("SELECT stable_id FROM source_items WHERE source = 'drive'").fetchone()[0].split("/")[0]
    proc, served = spawn(home, "--port", "0", env=env)
    yield served, f"/media/drive/{file_id}", (fixtures / "Meet Recordings" / hebrew.NAME).read_bytes()
    proc.terminate()
    proc.wait(timeout=10)
    proc.stdout.close()


def test_full_request_streams_the_file_with_range_support_advertised(media):
    served, path, data = media
    resp, body = served.request("GET", path, {"Cookie": f"librarian_token={served.token()}"})
    assert resp.status == 200
    assert resp.getheader("Accept-Ranges") == "bytes"
    assert resp.getheader("Content-Length") == str(len(data))
    assert body == data.decode()


def test_range_request_answers_206_with_content_range(media):
    served, path, data = media
    cookie = {"Cookie": f"librarian_token={served.token()}"}
    resp, body = served.request("GET", path, {**cookie, "Range": "bytes=0-9"})
    assert resp.status == 206
    assert resp.getheader("Content-Range") == f"bytes 0-9/{len(data)}"
    assert body == data[:10].decode()
    resp, body = served.request("GET", path, {**cookie, "Range": "bytes=-5"})
    assert (resp.status, body) == (206, data[-5:].decode())
    resp, body = served.request("GET", path, {**cookie, "Range": f"bytes=10-{len(data) + 500}"})
    assert (resp.status, body) == (206, data[10:].decode())


@pytest.mark.parametrize("bad", ["bytes=999999-", "bytes=9-3", "bytes=-", "items=0-5", "bytes=a-b"])
def test_bad_range_answers_416(media, bad):
    served, path, data = media
    resp, _ = served.request("GET", path, {"Cookie": f"librarian_token={served.token()}", "Range": bad})
    assert resp.status == 416
    assert resp.getheader("Content-Range") == f"bytes */{len(data)}"


def test_no_cookie_or_wrong_cookie_is_403_and_unknown_recording_404(media):
    served, path, _ = media
    assert served.request("GET", path)[0].status == 403
    assert served.request("GET", path, {"Cookie": "librarian_token=wrong"})[0].status == 403
    assert served.request("GET", "/media/drive/nope", {"Cookie": f"librarian_token={served.token()}"})[0].status == 404
