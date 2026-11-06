def key(name: str) -> str:
    """The form two spellings of one name share: case and whitespace folded."""
    return " ".join(name.casefold().split())
