import json

from librarian import config, db, locator, store
from librarian.query import core, envelope
from librarian.slack import permalink
from librarian.transcribe import confidence

help = "Print one Source item with all its revisions, or one Record by id, as JSON (read-only); the answer envelope sits beside its own fields"


def add_arguments(parser):
    parser.add_argument(
        "locator", help="<source>:<stable_id>[#<part>] (see librarian.locator), or a Record id"
    )


def _error(code, message):
    print(json.dumps({"error": {"code": code, "message": message}}))
    return 1


def run(args, ctx):
    record_id = int(args.locator) if args.locator.isdigit() else None
    try:
        loc = None if record_id else locator.parse(args.locator)
    except ValueError as err:
        return _error("bad_locator", str(err))
    try:
        conn = db.connect_ro(ctx.workspace)
    except db.SchemaOutdated as err:
        return _error(
            "schema_outdated", f"{err}; run `librarian serve` or `librarian import` to update it"
        )
    if record_id:
        with conn:
            record = core.current_view(conn, ctx.workspace, record_id, config.load())
        if record is None:
            return _error("not_found", f"no Record {record_id}")
        with conn:
            wrapped = envelope.build(conn, ctx.workspace, config.load(), [record])
        print(json.dumps({**wrapped, **record, "evidence": wrapped["evidence"]}, indent=2, ensure_ascii=False))
        return 0
    with conn:
        item = store.get_item(conn, ctx.workspace, loc.source, loc.stable_id)
    if item is None:
        return _error("not_found", f"no Source item {loc.source}:{loc.stable_id}")
    if loc.source == "slack":
        item["permalink"] = permalink.for_item(conn, ctx.workspace, loc.stable_id)
    if loc.source == "drive":
        item.update(confidence.describe(json.loads(item["revisions"][-1]["content"]), config.load()))
    if loc.part:
        item["part"] = loc.part
    with conn:
        wrapped = envelope.build(conn, ctx.workspace, config.load(), [])
    print(json.dumps({**wrapped, **item}, indent=2, ensure_ascii=False))
    return 0
