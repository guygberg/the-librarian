"""One module per route group. Each defines `ROUTES: list[Route]`; modules are discovered."""

import importlib
import os
import pkgutil
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from librarian import config
from librarian.link.errors import Invalid
from librarian.query import core

# Extra modules (comma-separated) let a test register a route without touching this package.
EXTRA_MODULES_ENV = "LIBRARIAN_ROUTE_MODULES"


@dataclass(frozen=True)
class File:
    """A handler's answer that is a file on disk, sent with Range support instead of as JSON."""

    path: Path
    content_type: str


@dataclass(frozen=True)
class Route:
    method: str
    pattern: str  # `<name>` matches one path segment
    handler: Callable  # (Request) -> (status, json-able)
    media: bool = False  # media GET routes also accept the cookie
    regex: re.Pattern = field(init=False, compare=False)

    def __post_init__(self):
        rx = re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", self.pattern)
        object.__setattr__(self, "regex", re.compile(rx + "$"))


Refused = Invalid  # the route-side name for a refused action: a status and a message


def field(body, key, kind, required=True):
    """A body value of `kind`: int, str (non-empty) or list (of integers)."""
    value = body.get(key) if isinstance(body, dict) else None
    if value is None and not required:
        return None
    if kind is list:
        if isinstance(value, list) and all(isinstance(v, int) and not isinstance(v, bool) for v in value):
            return value
        raise Refused(400, f"{key} must be a list of integers")
    if not isinstance(value, kind) or isinstance(value, bool) or value == "":
        raise Refused(400, f"{key} must be {'an integer' if kind is int else 'a non-empty string'}")
    return value


def mutating(do):
    """A POST handler: `do(conn, workspace, req)` returns the id whose new current view is the answer."""

    def handler(req):
        with req.rw() as conn:
            try:
                record_id = do(conn, req.workspace, req)
            except Refused as refused:
                return refused.status, {"error": refused.message}
            return 200, core.current_view(conn, req.workspace, record_id, config.load())

    return handler


def discover() -> list[Route]:
    names = [f"{__name__}.{m.name}" for m in pkgutil.iter_modules(__path__)]
    names += [n for n in os.environ.get(EXTRA_MODULES_ENV, "").split(",") if n]
    return [r for name in names for r in importlib.import_module(name).ROUTES]
