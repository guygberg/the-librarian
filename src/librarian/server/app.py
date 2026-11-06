import json
import mimetypes
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from librarian import db
from librarian.server import ranges, routes, security

STATIC = (Path(__file__).parent / "static").resolve()
STATIC_PREFIX = "/static/"
SHELL = STATIC / "index.html"
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
            if url.path.startswith(STATIC_PREFIX):
                return self._static(url.path.removeprefix(STATIC_PREFIX))
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
        if isinstance(payload, routes.File):
            return self._file(payload)
        self._json(status, payload)

    def _file(self, file: routes.File):
        size = file.path.stat().st_size
        try:
            span = ranges.parse(self.headers.get("Range"), size)
        except ranges.Unsatisfiable:
            return self._send(416, b"", "text/plain", [("Content-Range", f"bytes */{size}")])
        start, end = span or (0, size - 1)
        headers = [("Accept-Ranges", "bytes")]
        if span:
            headers.append(("Content-Range", f"bytes {start}-{end}/{size}"))
        self.send_response(206 if span else 200)
        self.send_header("Content-Type", file.content_type)
        self.send_header("Content-Length", str(max(end - start + 1, 0)))
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        if self.command == "HEAD":
            return
        with file.path.open("rb") as handle:
            handle.seek(start)
            left = end - start + 1
            try:
                while left > 0 and (chunk := handle.read(min(left, 1 << 16))):
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the player seeked away

    def _static(self, name):
        """The UI's own files. They hold no data and no token, so only the Host check applies."""
        if reason := security.check_host(self.headers, self.server.port):
            return self._json(403, {"error": reason})
        path = (STATIC / name).resolve()
        if not path.is_relative_to(STATIC) or not path.is_file():
            return self._json(404, {"error": "not found"})
        media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send(
            200,
            path.read_bytes(),
            f"{media}; charset=utf-8" if media.startswith("text/") else media,
        )

    def _shell(self):
        server = self.server
        if reason := security.check_host(self.headers, server.port):
            return self._json(403, {"error": reason})
        page = SHELL.read_text().replace("__TOKEN__", server.token).encode()
        cookie = f"{security.COOKIE_NAME}={server.token}; SameSite=Strict; HttpOnly; Path=/"
        self._send(200, page, "text/html; charset=utf-8", [("Set-Cookie", cookie)])

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = _handle
