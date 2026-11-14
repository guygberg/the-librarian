from librarian import db, engines, gate
from librarian.extract import suggest_stage
from librarian.importer.lock import LockHeld, workspace_lock

help = "Analyse stored source text for Suggestions (Tags, Items, Links); never part of Import"


def add_arguments(parser):
    parser.add_argument(
        "--max-calls",
        type=int,
        metavar="N",
        help="send at most N units to Claude this run, newest first (default: suggest_max_calls)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print how many units would be analysed, sending and writing nothing",
    )


def run(args, ctx):
    max_calls = ctx.config["suggest_max_calls"] if args.max_calls is None else args.max_calls
    if args.dry_run:
        conn = db.connect_ro(ctx.workspace)
        try:
            counts = suggest_stage.analyse(
                conn, ctx.workspace, engines.get_suggester(ctx.workspace), max_calls, ctx.config,
                dry_run=True,
            )  # fmt: skip
        finally:
            conn.close()
        print(
            f"dry run: eligible {counts.eligible}, deferred {counts.deferred}, "
            f"calls {min(counts.eligible, max(0, max_calls))}, none sent"
        )
        return 0
    status = gate.training_gate_status(ctx.config)
    if not status.allowed:
        print(f"librarian: suggest skipped, {status.reason}; {status.fix}")
        return 1
    try:
        with workspace_lock(ctx.workspace_dir):
            conn = db.connect_rw(ctx.workspace)
            try:
                counts = suggest_stage.analyse(
                    conn, ctx.workspace, engines.get_suggester(ctx.workspace), max_calls, ctx.config
                )
            finally:
                conn.close()
    except LockHeld as held:
        print(f"librarian: another import or suggest run is active ({held.holder})")
        return 1
    print(f"suggest: {counts.line()}")
    if counts.deferred:
        print("run suggest again to continue")
    return 1 if counts.failed else 0
