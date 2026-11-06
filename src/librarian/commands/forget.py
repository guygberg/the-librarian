from librarian import db, engines, forget
from librarian.importer.lock import LockHeld, workspace_lock
from librarian.slack import picks
from librarian.tty import require_terminal

help = "Delete a Slack conversation's imported items and the Records only it supports"


def add_arguments(parser):
    parser.add_argument("conversation", help="conversation id or name")


def _resolve(conn, ctx, text):
    """(id, label) of the conversation, or None. An id counts when it has stored items or is picked."""
    if forget.items_of(conn, ctx.workspace, text) or text in picks.picked_ids(conn, ctx.workspace):
        return text, text
    rows = picks.rows(engines.get_engines(ctx.workspace).slack.list_conversations(), set())
    match = [r for r in rows if text in (r["id"], r["name"])]
    return (match[0]["id"], match[0]["name"]) if match else None


def run(args, ctx):
    require_terminal()
    try:
        with workspace_lock(ctx.workspace_dir):
            conn = db.connect_rw(ctx.workspace)
            found = _resolve(conn, ctx, args.conversation)
            if found is None:
                raise SystemExit(f"librarian: no Slack conversation {args.conversation!r}")
            conversation_id, label = found
            count = len(forget.items_of(conn, ctx.workspace, conversation_id))
            print(f"{label}: {count} messages and every Record supported only by them would be deleted")
            try:
                answer = input(f"Type {label} to confirm: ").strip()
            except EOFError:
                answer = ""
            if answer != label:
                print("nothing deleted")
                return 1
            result = forget.forget(conn, ctx.workspace, conversation_id, label)
            print(f"forgot {label}: {result['items']} messages, {result['records']} Records")
            return 0
    except LockHeld as held:
        print(f"librarian: an import is running ({held.holder}); try again when it has finished")
        return 1
