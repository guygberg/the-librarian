from librarian import db, engines
from librarian.slack import picks
from librarian.tty import require_terminal

help = "Choose which Slack conversations are imported"


def add_arguments(parser):
    sub = parser.add_subparsers(dest="action", required=True)
    pick = sub.add_parser("pick", help="list conversations and edit the picked ones")
    pick.add_argument("--list", action="store_true", help="only print the list (read-only)")


def _show(rows):
    for n, r in enumerate(rows, 1):
        mark = "x" if r["picked"] else " "
        print(f"{n:3} [{mark}] {r['name']}  ({r['kind']}, {r['members']} members)")


def _numbers(answer, count):
    chosen = set()
    for token in answer.replace(",", " ").split():
        if not (token.isdigit() and 1 <= int(token) <= count):
            print(f"  not a number from 1 to {count}: {token}")
            return None
        chosen.add(int(token))
    return chosen


def run(args, ctx):
    if not args.list:
        require_terminal()
    conn = db.connect_rw(ctx.workspace)
    picks.seed_once(conn, ctx.workspace, ctx.workspace_dir)
    conversations = engines.get_engines(ctx.workspace).slack.list_conversations()
    picked = picks.picked_ids(conn, ctx.workspace)
    rows = picks.rows(conversations, picked)
    _show(rows)
    if args.list:
        return 0
    while True:
        try:
            answer = input("Numbers to pick or unpick, empty to save: ").strip()
        except EOFError:
            raise SystemExit("librarian: pick aborted, nothing saved") from None
        if not answer:
            break
        chosen = _numbers(answer, len(rows))
        if chosen is None:
            continue
        for n in chosen:
            rows[n - 1]["picked"] = not rows[n - 1]["picked"]
        _show(rows)
    on = [r["id"] for r in rows if r["picked"]]
    off = [r["id"] for r in rows if not r["picked"]]
    picks.edit_picks(conn, ctx.workspace, on, off)
    print(f"picked {len(on)} conversations")
    return 0
