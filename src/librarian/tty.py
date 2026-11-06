import sys


def require_terminal() -> None:
    """Refuse (exit 2, nothing written) when stdin is not a terminal."""
    if not sys.stdin.isatty():
        print(
            "librarian: this command changes data and needs a terminal; run it yourself.",
            file=sys.stderr,
        )
        sys.exit(2)
