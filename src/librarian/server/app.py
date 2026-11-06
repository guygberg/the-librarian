import json
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from librarian import db
from librarian.server import routes, security

SHELL = Path(__file__).parent / "static" / "index.html"
HOST = "127.0.0.1"


@dataclass
class Request:
    workspace: str
    method: str
    path: str
    query: str
    params: dict[str, str]
    body: Any

    @contextmanager
    def ro(self):
        conn = db.connect_ro(self.workspace)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def rw(self):
        conn = db.connect_rw(self.workspace)
        try:
            yield conn
        finally:
            conn.close()


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, workspace: str, port: int):
        self.workspace = workspace
        self.token = secrets.token_urlsafe(32)
        self.routes = routes.discover()
        super().__init__((HOST, port), Handler)

    @property
    def port(self) -> int:
        return self.server_address[1]


class Handler(BaseHTTPRequestHandler):
    server: Server

    def log_message(self, *args):
        pass

    def _send(self, status, body: bytes, content_type, headers=()):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status, payload):
        self._send(status, json.dumps(payload).encode(), "application/json")

    def _handle(self):
        server, method = self.server, self.command
        url = urlsplit(self.path)
        match = None
        for route in server.routes:
            m = route.regex.match(url.path)
            if m and route.method == method:
                match = route, m
                break

        if match is None and not url.path.startswith("/api/") and method in ("GET", "HEAD"):
            return self._shell()

        reason = security.check(
            method=method,
            headers=self.headers,
            port=server.port,
            token=server.token,
            media=bool(match and match[0].media),
        )
        if reason:
            return self._json(403, {"error": reason})
        if match is None:
            return self._json(404, {"error": "not found"})

        body = None
        if method not in security.SAFE_METHODS:
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                body = json.loads(raw or b"null")
            except ValueError:
                return self._json(400, {"error": "invalid JSON"})
        route, m = match
        req = Request(server.workspace, method, url.path, url.query, m.groupdict(), body)
        status, payload = route.handler(req)
        self._json(status, payload)

    def _shell(self):
        server = self.server
        if reason := security.check_host(self.headers, server.port):
            return self._json(403, {"error": reason})
        page = SHELL.read_text().replace("__TOKEN__", server.token).encode()
        cookie = f"{security.COOKIE_NAME}={server.token}; SameSite=Strict; HttpOnly; Path=/"
        self._send(200, page, "text/html; charset=utf-8", [("Set-Cookie", cookie)])

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = _handle
