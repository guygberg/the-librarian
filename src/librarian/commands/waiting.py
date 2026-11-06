from librarian.commands import print_answer
from librarian.query import waiting

help = "Items pending on someone and who owns the next step, as JSON (read-only)"


def add_arguments(parser):
    pass


def run(args, ctx):
    return print_answer(ctx, lambda conn: waiting.waiting(conn, ctx.workspace))
