import argparse
import os

from librarian import db, gate, launch
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
        help=(
            "transcribe that recording as he, en or mixed, "
            "overriding the flag in config and detection"
        ),
    )
    parser.add_argument(
        "--max-calls",
        type=int,
        metavar="N",
        help=(
            "send at most N units to Claude this run, newest first "
            "(default: extract_max_calls in config)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "run the local stages and print how many extraction calls an Import would make, "
            "sending nothing"
        ),
    )
    parser.add_argument("--older", metavar="CONVERSATION_ID", help=argparse.SUPPRESS)


def run(args, ctx):
    # `serve` starts its Import with no terminal; the person pressed the button,
    # and launch proves it.
    if not launch.granted():
        require_terminal()
    try:
        languages = dict(language.parse_override(text) for text in args.language)
    except ValueError as err:
        print(f"librarian: {err}")
        return 2
    return execute(
        ctx, older=args.older, languages=languages, max_calls=args.max_calls, dry_run=args.dry_run
    )


def _before_extract(stages):
    names = [s.name for s in stages]
    return stages[: names.index("extract")] if "extract" in names else stages


def count_calls(ctx, languages=None, max_calls=None) -> tuple[int, int]:
    """Run the local stages and return (extraction calls an Import would make, failed items).

    Sends nothing. The local stages only fetch and transcribe; no Record is written.
    Raises LockHeld during an Import.
    """
    if max_calls is None:
        max_calls = ctx.config["extract_max_calls"]
    with workspace_lock(ctx.workspace_dir):
        conn = db.connect_rw(ctx.workspace)
        try:
            run = runner.start_run(conn, ctx.workspace, os.getpid())
            stages = load_stages(ctx.workspace, None, languages, max_calls)
            failed = runner.run_import(run, _before_extract(stages), lambda _: None)
            return min(
                len(extract_stage.stale_units(conn, ctx.workspace)), max(0, max_calls)
            ), failed
        finally:
            conn.close()


def execute(ctx, older=None, languages=None, max_calls=None, dry_run=False):
    """One Import under the Workspace lock.

    `older` limits fetching to that Slack conversation's older history.
    """
    if max_calls is None:
        max_calls = ctx.config["extract_max_calls"]
    try:
        if dry_run:
            calls, failed = count_calls(ctx, languages, max_calls)
            print(f"dry run: {calls} extraction calls would be made, none sent")
            return 1 if failed else 0
        with workspace_lock(ctx.workspace_dir):
            conn = db.connect_rw(ctx.workspace)
            run = runner.start_run(conn, ctx.workspace, os.getpid())
            stages = load_stages(ctx.workspace, older, languages, max_calls)
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
                "SELECT stage, error, COUNT(*) FROM import_item_stages"
                " WHERE run_id = ? AND status = 'failed'"
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
