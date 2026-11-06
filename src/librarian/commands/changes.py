from librarian.commands import print_answer
from librarian.query import changes

help = "What changed since the last meeting (or the last 7 days), as JSON (read-only)"


def add_arguments(parser):
    parser.add_argument("--project", help="project name or Alias; default is the whole workspace")


def run(args, ctx):
    return print_answer(ctx, lambda conn: changes.changes(conn, ctx.workspace, args.project))
