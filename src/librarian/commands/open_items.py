import json

from librarian import db
from librarian.query import open_items

help = "Open items: Needs attention, Waiting on others, Other open, as JSON (read-only)"


def add_arguments(parser):
    pass


def run(args, ctx):
    try:
        conn = db.connect_ro(ctx.workspace)
    except db.SchemaOutdated as err:
        message = f"{err}; run `librarian serve` or `librarian import` to update it"
        print(json.dumps({"error": {"code": "schema_outdated", "message": message}}))
        return 1
    with conn:
        answer = open_items.open_items(conn, ctx.workspace)
    print(json.dumps(answer, indent=2, ensure_ascii=False))
    return 0
