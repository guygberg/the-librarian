import os

from librarian import db
from librarian.importer import progress, runner
from librarian.importer.lock import LockHeld, workspace_lock
from librarian.importer.stages import load_stages
from librarian.tty import require_terminal

help = "Import sources into the Workspace (fetch, transcribe, normalise, extract, link)"


def add_arguments(parser):
    pass


def run(args, ctx):
    require_terminal()
    try:
        with workspace_lock(ctx.workspace_dir):
            conn = db.connect_rw(ctx.workspace)
            run = runner.start_run(conn, ctx.workspace, os.getpid())
            failed = runner.run_import(run, load_stages(), print)
            print(f"import finished, {failed} failed")
            return 1 if failed else 0
    except LockHeld as held:
        print(f"librarian: another import is running ({held.holder})")
        try:
            print(progress.running_progress(db.connect_ro(ctx.workspace)))
        except db.SchemaOutdated:
            pass
        return 1
