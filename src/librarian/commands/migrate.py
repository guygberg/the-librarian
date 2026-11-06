from librarian import db

help = "Create or migrate the Workspace database"


def add_arguments(parser):
    parser.add_argument(
        "--status", action="store_true", help="Print version and pending count; change nothing"
    )


    parser.add_argument(
        "--existing-only",
        action="store_true",
        help="Do nothing when the Workspace has no database yet (used by make install)",
    )


def run(args, ctx):
    path = db.db_path(ctx.workspace)
    latest = db.latest_version()
    if args.existing_only and not path.exists():
        return 0
    if args.status:
        version = db.current_version(path)
        print(f"version {version}, {len(_pending(version))} pending")
        return 0
    db.connect_rw(ctx.workspace).close()
    print(f"version {latest}")
    return 0


def _pending(version):
    return [v for v, _ in db.migration_files() if v > version]
