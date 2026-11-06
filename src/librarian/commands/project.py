import json

from librarian import db
from librarian.query import project

help = (
    "One project's status, owners, deadlines, latest decision and main blocker "
    "with Evidence, as JSON (read-only)"
)


def add_arguments(parser):
    parser.add_argument("name", help="project name or Alias; an unclear name returns candidates")


def run(args, ctx):
    try:
        conn = db.connect_ro(ctx.workspace)
    except db.SchemaOutdated as err:
        message = f"{err}; run `librarian serve` or `librarian import` to update it"
        print(json.dumps({"error": {"code": "schema_outdated", "message": message}}))
        return 1
    with conn:
        answer = project.project(conn, ctx.workspace, args.name)
    print(json.dumps(answer, indent=2, ensure_ascii=False))
    return 0
