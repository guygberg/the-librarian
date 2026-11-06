from librarian.commands import print_answer
from librarian.query import blocked

help = "Open blockers and what they block, as JSON (read-only)"


def add_arguments(parser):
    parser.add_argument("--project", help="project name or Alias; default is the whole workspace")


def run(args, ctx):
    return print_answer(ctx, lambda conn: blocked.blocked(conn, ctx.workspace, args.project))
