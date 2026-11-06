"""One module per route group. Each defines `ROUTES: list[Route]`; modules are discovered."""

import importlib
import os
import pkgutil
import re
from collections.abc import Callable
from dataclasses import dataclass, field

# Extra modules (comma-separated) let a test register a route without touching this package.
EXTRA_MODULES_ENV = "LIBRARIAN_ROUTE_MODULES"


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


def discover() -> list[Route]:
    names = [f"{__name__}.{m.name}" for m in pkgutil.iter_modules(__path__)]
    names += [n for n in os.environ.get(EXTRA_MODULES_ENV, "").split(",") if n]
    return [r for name in names for r in importlib.import_module(name).ROUTES]
