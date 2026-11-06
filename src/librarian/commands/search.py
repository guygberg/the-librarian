import json

from librarian import db
from librarian.query import search

help = "Search Source items; prints passages with locators as JSON (read-only)"


def add_arguments(parser):
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=20)


def run(args, ctx):
    try:
        conn = db.connect_ro(ctx.workspace)
    except db.SchemaOutdated as err:
        message = f"{err}; run `librarian serve` or `librarian import` to update it"
        print(json.dumps({"error": {"code": "schema_outdated", "message": message}}))
        return 1
    with conn:
        answer = search.search(conn, ctx.workspace, args.query, args.limit)
    print(json.dumps(answer, indent=2, ensure_ascii=False))
    return 0
