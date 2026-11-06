from pathlib import Path

from librarian import backup

help = "Write a dated backup archive (database snapshot, Slack list, config) to a folder"


def add_arguments(parser):
    parser.add_argument(
        "folder",
        type=Path,
        help="where to write the archive; do not use a Drive-synced folder (a sync client can upload a half-written file)",
    )


def run(args, ctx):
    try:
        print(backup.create(ctx.workspace, args.folder))
    except backup.BackupError as err:
        print(f"librarian: {err}")
        return 1
    return 0
