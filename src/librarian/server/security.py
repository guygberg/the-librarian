"""Request guards. Every check returns a reason string to refuse with 403, or None to allow."""

import hmac

TOKEN_HEADER = "X-Librarian-Token"
COOKIE_NAME = "librarian_token"
SAFE_METHODS = {"GET", "HEAD"}


def allowed_hosts(port: int) -> set[str]:
    return {f"127.0.0.1:{port}", f"localhost:{port}"}


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def _cookie(header: str, name: str) -> str:
    for part in header.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return ""


def check_host(headers, port) -> str | None:
    return None if headers.get("Host", "") in allowed_hosts(port) else "foreign host"


def check(*, method, headers, port, token, media) -> str | None:
    if reason := check_host(headers, port):
        return reason
    if method not in SAFE_METHODS:
        origin = headers.get("Origin")
        if origin is not None and origin.removeprefix("http://") not in allowed_hosts(port):
            return "foreign origin"
        if headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return "writes must be application/json"
    supplied = headers.get(TOKEN_HEADER, "")
    if not supplied and media and method in SAFE_METHODS:
        supplied = _cookie(headers.get("Cookie", ""), COOKIE_NAME)
    if not supplied or not _same(supplied, token):
        return "missing or wrong token"
    return None
