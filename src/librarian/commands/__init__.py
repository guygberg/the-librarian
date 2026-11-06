"""One module per command; scanned by `librarian.cli`."""

import json
from collections.abc import Callable
from typing import Any

from librarian import db


def print_answer(ctx, ask: Callable[[Any], dict[str, Any]]) -> int:
    """Run the read-only query `ask(conn)` and print its JSON.

    An outdated database says how to update it.
    """
    try:
        conn = db.connect_ro(ctx.workspace)
    except db.SchemaOutdated as err:
        message = f"{err}; run `librarian serve` or `librarian import` to update it"
        print(json.dumps({"error": {"code": "schema_outdated", "message": message}}))
        return 1
    with conn:
        answer = ask(conn)
    print(json.dumps(answer, indent=2, ensure_ascii=False))
    return 0
