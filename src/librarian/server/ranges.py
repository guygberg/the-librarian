"""HTTP `Range: bytes=` for one file: a single range, answered 206, or refused 416."""

import re

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


class Unsatisfiable(ValueError):
    pass


def parse(header: str | None, size: int) -> tuple[int, int] | None:
    """Inclusive (first, last) byte to send, or None to send the whole file."""
    if not header:
        return None
    match = _RANGE.fullmatch(header.strip())
    if match is None or not any(match.groups()):
        raise Unsatisfiable(header)
    first, last = match.groups()
    if first == "":  # suffix: the last N bytes
        start, end = max(size - int(last), 0), size - 1
    else:
        start, end = int(first), min(int(last), size - 1) if last else size - 1
    if size == 0 or start > end or start >= size:
        raise Unsatisfiable(header)
    return start, end
