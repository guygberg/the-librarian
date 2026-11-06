import json

from librarian import db, locator, store
from librarian.slack import permalink

help = "Print one Source item with all its revisions as JSON (read-only)"


def add_arguments(parser):
    parser.add_argument("locator", help="<source>:<stable_id>[#<part>], see librarian.locator")


def _error(code, message):
    print(json.dumps({"error": {"code": code, "message": message}}))
    return 1


def run(args, ctx):
    try:
        loc = locator.parse(args.locator)
    except ValueError as err:
        return _error("bad_locator", str(err))
    try:
        conn = db.connect_ro(ctx.workspace)
    except db.SchemaOutdated as err:
        return _error(
            "schema_outdated", f"{err}; run `librarian serve` or `librarian import` to update it"
        )
    with conn:
        item = store.get_item(conn, ctx.workspace, loc.source, loc.stable_id)
    if item is None:
        return _error("not_found", f"no Source item {loc.source}:{loc.stable_id}")
    if loc.source == "slack":
        item["permalink"] = permalink.for_item(conn, ctx.workspace, loc.stable_id)
    if loc.part:
        item["part"] = loc.part
    print(json.dumps(item, indent=2, ensure_ascii=False))
    return 0
