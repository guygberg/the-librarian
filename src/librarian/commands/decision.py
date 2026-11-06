from librarian.commands import print_answer
from librarian.query import decision

help = "A decision with its reasoning and Evidence, as JSON (read-only)"


def add_arguments(parser):
    parser.add_argument("topic", help="words from the decision, such as 'webhook v1'")


def run(args, ctx):
    return print_answer(ctx, lambda conn: decision.decision(conn, ctx.workspace, args.topic))
