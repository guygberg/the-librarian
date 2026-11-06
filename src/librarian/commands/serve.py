from librarian import db
from librarian.server.app import Server

help = "Serve the Librarian UI on 127.0.0.1 (foreground)"


def add_arguments(parser):
    parser.add_argument("--port", type=int, default=8765)


def run(args, ctx):
    db.connect_rw(ctx.workspace).close()
    server = Server(ctx.workspace, args.port)
    print(f"Librarian at http://127.0.0.1:{server.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
