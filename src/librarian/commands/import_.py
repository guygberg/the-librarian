import os

from librarian import db, gate
from librarian.extract import stage as extract_stage
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
    parser.add_argument(
        "--max-calls",
        type=int,
        metavar="N",
        help="send at most N units to Claude this run, newest first (default: extract_max_calls in config)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run the local stages and print how many extraction calls an Import would make, sending nothing",
    )


def run(args, ctx):
    require_terminal()
    try:
        languages = dict(language.parse_override(text) for text in args.language)
    except ValueError as err:
        print(f"librarian: {err}")
        return 2
    return execute(ctx, languages=languages, max_calls=args.max_calls, dry_run=args.dry_run)


def _before_extract(stages):
    names = [s.name for s in stages]
    return stages[: names.index("extract")] if "extract" in names else stages


def execute(ctx, older=None, languages=None, max_calls=None, dry_run=False):
    """One Import under the Workspace lock; `older` limits fetching to that Slack conversation's older history."""
    if max_calls is None:
        max_calls = ctx.config["extract_max_calls"]
    try:
        with workspace_lock(ctx.workspace_dir):
            conn = db.connect_rw(ctx.workspace)
            run = runner.start_run(conn, ctx.workspace, os.getpid())
            stages = load_stages(ctx.workspace, older, languages, max_calls)
            if dry_run:
                # The local stages only fetch and transcribe; no Record is written and nothing goes to Claude.
                failed = runner.run_import(run, _before_extract(stages), lambda _: None)
                calls = min(len(extract_stage.stale_units(conn, ctx.workspace)), max(0, max_calls))
                print(f"dry run: {calls} extraction calls would be made, none sent")
                return 1 if failed else 0
            status = gate.training_gate_status(ctx.config)
            if not status.allowed:
                # Everything from extract on sends work text to Claude, so none of it runs.
                stages = _before_extract(stages)
            failed = runner.run_import(run, stages, print)
            print(f"import finished, {failed} failed")
            for stage in stages:
                if stage.summary:
                    print(stage.summary())
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
