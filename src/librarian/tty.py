import sys


def require_terminal() -> None:
    """Refuse (exit 2, nothing written) when stdin is not a terminal."""
    if not sys.stdin.isatty():
        sys.exit("librarian: this command changes data and needs a terminal; run it yourself.")
