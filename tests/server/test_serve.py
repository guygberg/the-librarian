import socket

import pytest

from librarian import paths
from librarian.importer.lock import workspace_lock
from support.serve import spawn

MEDIA_ROUTE = """
from librarian.server.routes import Route
ROUTES = [Route("GET", "/media/<name>", lambda req: (200, {"ok": 1}), media=True)]
"""
JSON = {"Content-Type": "application/json"}


@pytest.fixture
def start(tmp_path, home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    procs = []

    def _start(*args):
        (tmp_path / "plug").mkdir(exist_ok=True)
        (tmp_path / "plug" / "media_probe.py").write_text(MEDIA_ROUTE)
        env = {"PYTHONPATH": str(tmp_path / "plug"), "LIBRARIAN_ROUTE_MODULES": "media_probe"}
        proc, served = spawn(home, *args, env=env)
        procs.append(proc)
        return served

    yield _start
    for proc in procs:
        proc.terminate()
        proc.wait(timeout=10)
        proc.stdout.close()


def test_page_loads_without_login_and_embeds_token(start):
    s = start("--port", "0")
    resp, page = s.request("GET", "/")
    assert resp.status == 200 and len(s.token()) > 20
    deep, deep_page = s.request("GET", "/people/42")
    assert deep.status == 200 and deep_page == page
    assert "SameSite=Strict" in resp.getheader("Set-Cookie")
    assert "HttpOnly" in resp.getheader("Set-Cookie")


def test_foreign_host_refused(start):
    s = start("--port", "0")
    for path in ("/", "/api/status"):
        resp, _ = s.request("GET", path, {"X-Librarian-Token": s.token()}, host="evil.test")
        assert resp.status == 403
    resp, _ = s.request("GET", "/", host=f"localhost:{s.port}")
    assert resp.status == 200


def test_api_needs_token(start):
    s = start("--port", "0")
    assert s.request("GET", "/api/status")[0].status == 403
    assert s.request("GET", "/api/status", {"X-Librarian-Token": "wrong"})[0].status == 403
    resp, data = s.request("GET", "/api/status", {"X-Librarian-Token": s.token()})
    assert resp.status == 200 and '"schema_version"' in data


def test_writes_checked_for_origin_and_content_type(start):
    s = start("--port", "0")
    auth = {"X-Librarian-Token": s.token()}
    foreign = {**auth, **JSON, "Origin": "http://evil.test"}
    assert s.request("POST", "/api/x", foreign, "{}")[0].status == 403
    plain = {**auth, "Content-Type": "text/plain"}
    assert s.request("POST", "/api/x", plain, "{}")[0].status == 403
    same = {**auth, **JSON, "Origin": f"http://127.0.0.1:{s.port}"}
    assert s.request("POST", "/api/x", same, "{}")[0].status == 404


def test_cookie_accepted_only_on_media_get(start):
    s = start("--port", "0")
    assert s.request("GET", "/media/a")[0].status == 403
    cookie = {"Cookie": f"librarian_token={s.token()}"}
    assert s.request("GET", "/media/a", cookie)[0].status == 200
    assert s.request("GET", "/api/status", cookie)[0].status == 403


def test_binds_loopback_only_and_port_flag(start):
    s = start("--port", "0")
    assert s.proc.poll() is None
    lan = next(
        (a for a in socket.gethostbyname_ex(socket.gethostname())[2] if not a.startswith("127.")),
        None,
    )
    if lan:
        with pytest.raises(OSError), socket.create_connection((lan, s.port), timeout=2):
            pass
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
    t = start("--port", str(free))
    assert t.port == free


def test_reads_work_while_import_lock_held(start, home):
    s = start("--port", "0")
    with workspace_lock(paths.workspace_dir(paths.DEFAULT_WORKSPACE)):
        resp, _ = s.request("GET", "/api/status", {"X-Librarian-Token": s.token()})
    assert resp.status == 200
