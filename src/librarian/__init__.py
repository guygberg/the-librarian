"""The Librarian: a work memory bank.

Conventions every ticket relies on:

- src layout; the package is `librarian`, one console command `librarian`.
- A command is one module, `src/librarian/commands/<name>.py`, with
  `help: str`, `add_arguments(parser)` and `run(args, ctx) -> int`. The
  package is scanned, so there is no central list to edit.
- `ctx` is a `cli.Context` (workspace name, data folder, config).
- Writing admin commands call `tty.require_terminal()` first.
- Tests for an area live in `tests/<area>/` with their own `conftest.py`;
  shared helpers live in `tests/support/`.
- The end-of-ticket check is always `make check`.
"""
