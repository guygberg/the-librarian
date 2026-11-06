import os

from librarian import db, gate
from librarian.importer import progress, runner
from librarian.importer.lock import LockHeld, workspace_lock
from librarian.importer.stages import load_stages
from librarian.transcribe import language
from librarian.tty import require_terminal

help = "Import sources into the Workspace (fetch, transcribe, normalise, extract, link)"


def add_arguments(parser):
    parser.add_argument(
        "--language",
        action="append",
        default=[],
        metavar="FILE_OR_TITLE=LANG",
        help="transcribe that recording as he, en or mixed, overriding the flag in config and detection",
    )


def run(args, ctx):
    require_terminal()
    try:
        languages = dict(language.parse_override(text) for text in args.language)
    except ValueError as err:
        print(f"librarian: {err}")
        return 2
    return execute(ctx, languages=languages)


def execute(ctx, older=None, languages=None):
    """One Import under the Workspace lock; `older` limits fetching to that Slack conversation's older history."""
    try:
        with workspace_lock(ctx.workspace_dir):
            conn = db.connect_rw(ctx.workspace)
            run = runner.start_run(conn, ctx.workspace, os.getpid())
            stages = load_stages(ctx.workspace, older, languages)
            status = gate.training_gate_status(ctx.config)
            if not status.allowed:
                # Everything from extract on sends work text to Claude, so none of it runs.
                names = [s.name for s in stages]
                stages = stages[: names.index("extract")] if "extract" in names else stages
            failed = runner.run_import(run, stages, print)
            print(f"import finished, {failed} failed")
            for stage, error, count in conn.execute(
                "SELECT stage, error, COUNT(*) FROM import_item_stages WHERE run_id = ? AND status = 'failed'"
                " GROUP BY stage, error",
                (run.id,),
            ):
                print(f"failed at {stage} ({count} items): {error}")
            if not status.allowed:
                print(f"librarian: extraction skipped, {status.reason}; {status.fix}")
                return 1
            return 1 if failed else 0
    except LockHeld as held:
        print(f"librarian: another import is running ({held.holder})")
        try:
            print(progress.running_progress(db.connect_ro(ctx.workspace)))
        except db.SchemaOutdated:
            pass
        return 1
