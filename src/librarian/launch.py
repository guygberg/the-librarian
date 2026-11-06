"""How `serve` proves to the `import` child it starts that a person pressed the button.

This only raises the bar against a casual injected `librarian import`: any process of the same
user can copy what serve does here. The nonce travels in the child's environment plus an
inherited pipe, never on the command line, in a file or in the log.
"""

import hmac
import os
import secrets

ENV = "LIBRARIAN_IMPORT_LAUNCH"


def grant() -> tuple[dict[str, str], int]:
    """(environment entry for the child, read end to pass with pass_fds).

    The caller closes the read end after Popen.
    """
    nonce = secrets.token_hex(16)
    read_fd, write_fd = os.pipe()
    os.write(write_fd, nonce.encode())
    os.close(write_fd)
    return {ENV: f"{read_fd}:{nonce}"}, read_fd


def granted() -> bool:
    """True only when the environment's nonce matches the one serve wrote to the inherited pipe."""
    value = os.environ.pop(ENV, "")
    fd, _, nonce = value.partition(":")
    if not fd.isdigit() or not nonce:
        return False
    try:
        sent = os.read(int(fd), 64).decode()
        os.close(int(fd))
    except (OSError, UnicodeDecodeError):
        return False
    return hmac.compare_digest(sent, nonce)
