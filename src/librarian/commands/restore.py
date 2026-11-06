from pathlib import Path

from librarian import backup
from librarian.importer.lock import LockHeld, workspace_lock
from librarian.tty import require_terminal

help = "Restore a backup archive into an empty data folder (terminal only)"


def add_arguments(parser):
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace a non-empty data folder after typing the Workspace name to confirm",
    )


def run(args, ctx):
    require_terminal()
    try:
        backup.check_restorable(args.archive)
        with workspace_lock(ctx.workspace_dir):
            if not backup.is_empty(ctx.workspace):
                if not args.overwrite:
                    print(f"librarian: {ctx.workspace_dir} is not empty; pass --overwrite to replace it")
                    return 1
                try:
                    answer = input(f"This replaces the Workspace's data. Type {ctx.workspace} to confirm: ").strip()
                except EOFError:
                    answer = ""
                if answer != ctx.workspace:
                    print("nothing restored")
                    return 1
            backup.restore(ctx.workspace, args.archive)
            print(f"restored {args.archive} into {ctx.workspace_dir}")
            return 0
    except backup.BackupError as err:
        print(f"librarian: {err}")
        return 1
    except LockHeld as held:
        print(f"librarian: an import is running ({held.holder}); try again when it has finished")
        return 1
