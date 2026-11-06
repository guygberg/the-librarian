from librarian import db

help = "Create or migrate the Workspace database"


def add_arguments(parser):
    parser.add_argument(
        "--status", action="store_true", help="Print version and pending count; change nothing"
    )


def run(args, ctx):
    path = db.db_path(ctx.workspace)
    latest = db.latest_version()
    if args.status:
        version = db.current_version(path)
        print(f"version {version}, {len(_pending(version))} pending")
        return 0
    db.connect_rw(ctx.workspace).close()
    print(f"version {latest}")
    return 0


def _pending(version):
    return [v for v, _ in db.migration_files() if v > version]
