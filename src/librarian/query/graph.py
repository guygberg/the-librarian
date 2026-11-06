"""The Relations graph: the neighbourhood of a Record or Person as nodes and typed edges. Read-only (`db.connect_ro`).

Traversal ignores edge direction. Superseded and dropped Records keep their edges; nothing is filtered by lifecycle.
"""

import sqlite3
from typing import Any

from librarian.link import review

KINDS = ("belongs_to", "owner", "waiting_on", "blocks", "supersedes", "related_to", "mentions", "evidence")
MAX_HOPS = 3

Node = tuple[str, int]  # (type, id)


class BadGraphRequest(ValueError):
    pass


def parse_center(text: str) -> Node:
    kind, _, number = text.rpartition(":")
    if number.isdigit() and kind in ("", "record", "person"):
        return (kind or "record", int(number))
    raise BadGraphRequest(f"bad center {text!r}: expected record:<id> or person:<id>")


def _edges(conn: sqlite3.Connection, workspace: str, kinds: tuple[str, ...]) -> list[tuple[str, Node, Node]]:
    marks = ", ".join("?" * len(kinds))
    edges = [
        (type_, (from_type, from_id), (to_type, to_id))
        for type_, from_type, from_id, to_type, to_id in conn.execute(
            f"SELECT type, from_type, from_id, to_type, to_id FROM links WHERE workspace = ? AND type IN ({marks}) ORDER BY id",
            (workspace, *kinds),
        )
    ]
    if "owner" in kinds:  # the owner column is the owner Link whether or not a row was written for it
        have = {(a, b) for t, a, b in edges if t == "owner"}
        for record_id, person_id in conn.execute(
            "SELECT id, owner_person_id FROM records WHERE workspace = ? AND owner_person_id IS NOT NULL ORDER BY id", (workspace,)
        ):
            pair = (("record", record_id), ("person", person_id))
            if pair not in have:
                edges.append(("owner", *pair))
    return edges


def _label(conn: sqlite3.Connection, workspace: str, node: Node) -> dict[str, Any]:
    type_, id_ = node
    if type_ == "record":
        row = conn.execute("SELECT kind, title, lifecycle FROM records WHERE workspace = ? AND id = ?", (workspace, id_)).fetchone()
        return {"record_kind": row[0], "title": row[1], "lifecycle": row[2]} if row else {}
    if type_ == "person":
        row = conn.execute("SELECT name FROM persons WHERE workspace = ? AND id = ?", (workspace, id_)).fetchone()
        aliases = [a for (a,) in conn.execute("SELECT alias FROM aliases WHERE workspace = ? AND person_id = ? ORDER BY id", (workspace, id_))]
        return {"title": row[0], "aliases": aliases} if row else {}
    row = conn.execute("SELECT source, stable_id FROM source_items WHERE workspace = ? AND id = ?", (workspace, id_)).fetchone()
    return {"title": f"{row[0]}:{row[1]}"} if row else {}


def _evidence(conn: sqlite3.Connection, workspace: str, record_id: int) -> list[dict[str, Any]]:
    return [
        {"locator": loc, "quote": quote, "role": role}
        for loc, quote, role in conn.execute(
            "SELECT locator, quote, role FROM evidence WHERE workspace = ? AND record_id = ? ORDER BY id", (workspace, record_id)
        )
    ]


def neighbourhood(
    conn: sqlite3.Connection, workspace: str, center: Node, hops: int, kinds: tuple[str, ...]
) -> dict[str, Any] | None:
    """None when the centre does not exist."""
    if not _label(conn, workspace, center):
        return None
    edges = _edges(conn, workspace, kinds)
    around: dict[Node, list[Node]] = {}
    for _, a, b in edges:
        around.setdefault(a, []).append(b)
        around.setdefault(b, []).append(a)
    distance = {center: 0}
    frontier = [center]
    for hop in range(1, hops + 1):
        reached = [n for node in frontier for n in around.get(node, []) if n not in distance]
        distance.update({n: hop for n in reached})
        frontier = list(dict.fromkeys(reached))
    nodes = []
    for node, hop in sorted(distance.items(), key=lambda kv: (kv[1], kv[0])):
        entry = {"id": f"{node[0]}:{node[1]}", "type": node[0], "hop": hop, **_label(conn, workspace, node)}
        if node[0] == "record":
            suggested = review.for_record(conn, workspace, node[1])
            if suggested:
                entry["suggested"] = suggested
        nodes.append(entry)
    out_edges = [
        {
            "kind": kind,
            "from": f"{a[0]}:{a[1]}",
            "to": f"{b[0]}:{b[1]}",
            "evidence": _evidence(conn, workspace, a[1]) if a[0] == "record" else [],
        }
        for kind, a, b in edges
        if a in distance and b in distance
    ]
    return {"center": f"{center[0]}:{center[1]}", "hops": hops, "nodes": nodes, "edges": out_edges}
