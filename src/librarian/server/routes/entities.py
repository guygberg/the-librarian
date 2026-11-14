"""User-authored entities and their own columns: create and edit items, tags and people;
an item's priority and notes, a person's or tag's favorite, a tag's color; workspace settings."""

import json
import re

from librarian import events
from librarian.clock import utc_now_iso
from librarian.link import people, project_actions
from librarian.server.routes import Refused, Route, field


def text(body, key, limit=5000, required=False):
    if not isinstance(body, dict):
        raise Refused(400, "invalid body")
    value = body.get(key, "")
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise Refused(400, f"invalid {key}")
    return value.strip()


def _target(conn, req, table, column="id"):
    id_ = int(req.params["id"])
    if not conn.execute(
        f"SELECT 1 FROM {table} WHERE workspace = ? AND {column} = ?", (req.workspace, id_)
    ).fetchone():
        raise Refused(404, "not found")
    return id_


def _bool(body, key):
    if not isinstance(body, dict) or not isinstance(body.get(key), bool):
        raise Refused(400, f"invalid {key}")
    return body[key]


def get_settings(req):
    with req.ro() as conn:
        row = conn.execute(
            "SELECT sound FROM settings WHERE workspace = ?", (req.workspace,)
        ).fetchone()
    return 200, {"sound": bool(row and row[0])}


def save_settings(req):
    try:
        if not isinstance(req.body, dict) or req.body.keys() - {"sound"}:
            raise Refused(400, "unknown setting")
        sound = _bool(req.body, "sound")
        with req.rw() as conn:
            conn.execute(
                "INSERT INTO settings (workspace, sound) VALUES (?, ?)"
                " ON CONFLICT DO UPDATE SET sound = excluded.sound",
                (req.workspace, int(sound)),
            )
            conn.commit()
        return 200, {"sound": sound}
    except Refused as e:
        return e.status, {"error": e.message}


def set_priority(req):
    try:
        body = req.body
        value = body.get("priority") if isinstance(body, dict) else None
        if type(value) is not int or not 0 <= value <= 100:
            raise Refused(400, "invalid priority")
        with req.rw() as conn:
            id_ = _target(conn, req, "items")
            conn.execute(
                "UPDATE items SET priority = ? WHERE workspace = ? AND id = ?",
                (value, req.workspace, id_),
            )
            conn.commit()
        return 200, {"id": id_, "priority": value}
    except (ValueError, TypeError):
        return 400, {"error": "invalid id"}
    except Refused as e:
        return e.status, {"error": e.message}


def add_note(req):
    """Append one private note; the server stamps its time."""
    try:
        note = {"text": text(req.body, "text", 5000, True), "time": utc_now_iso()}
        with req.rw() as conn:
            conn.execute("BEGIN IMMEDIATE")
            id_ = _target(conn, req, "items")
            (raw,) = conn.execute(
                "SELECT notes FROM items WHERE workspace = ? AND id = ?", (req.workspace, id_)
            ).fetchone()
            notes = json.loads(raw)
            if len(notes) >= 1000:
                raise Refused(400, "too many notes")
            notes.append(note)
            conn.execute(
                "UPDATE items SET notes = ? WHERE workspace = ? AND id = ?",
                (json.dumps(notes), req.workspace, id_),
            )
            conn.commit()
        return 200, {"id": id_, "notes": notes}
    except (ValueError, TypeError):
        return 400, {"error": "invalid id"}
    except Refused as e:
        return e.status, {"error": e.message}


def favorite_person(req):
    try:
        on = _bool(req.body, "favorite")
        with req.rw() as conn:
            id_ = _target(conn, req, "people")
            conn.execute(
                "UPDATE people SET favorite = ? WHERE workspace = ? AND id = ?",
                (int(on), req.workspace, id_),
            )
            conn.commit()
        return 200, {"id": id_, "favorite": on}
    except (ValueError, TypeError):
        return 400, {"error": "invalid id"}
    except Refused as e:
        return e.status, {"error": e.message}


def style_tag(req):
    """A tag's favorite star and accent color; either may be sent alone."""
    try:
        body = req.body
        if not isinstance(body, dict) or not body or body.keys() - {"favorite", "color"}:
            raise Refused(400, "unknown setting")
        changes = {}
        if "favorite" in body:
            changes["favorite"] = int(_bool(body, "favorite"))
        if "color" in body:
            color = body["color"]
            if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise Refused(400, "invalid color")
            changes["color"] = color
        with req.rw() as conn:
            id_ = _target(conn, req, "tags", "item_id")
            conn.execute(
                f"UPDATE tags SET {', '.join(f'{k} = ?' for k in changes)}"
                " WHERE workspace = ? AND item_id = ?",
                (*changes.values(), req.workspace, id_),
            )
            conn.commit()
        shown = {k: bool(v) if k == "favorite" else v for k, v in changes.items()}
        return 200, {"id": id_, **shown}
    except (ValueError, TypeError):
        return 400, {"error": "invalid id"}
    except Refused as e:
        return e.status, {"error": e.message}


def profile_fields(body):
    return {
        key: text(body, key, 254 if key == "email" else 100) or None
        for key in ("slack_id", "email", "role", "department")
    }


def check_slack(conn, workspace, slack_id, person_id=None):
    if slack_id and any(
        pid != person_id and alias == people.SLACK + slack_id
        for pid, alias in people.alias_rows(conn, workspace)
    ):
        raise Refused(409, "Slack ID already belongs to another person")


def profile_aliases(body):
    aliases = body.get("aliases", [])
    if (
        not isinstance(aliases, list)
        or len(aliases) > 100
        or not all(isinstance(a, str) and a.strip() and len(a) <= 254 for a in aliases)
    ):
        raise Refused(400, "aliases must be a list of names")
    return list(dict.fromkeys(a.strip() for a in aliases))


def profile(req):
    try:
        id_ = int(req.params["id"])
        name = text(req.body, "name", 120, True)
        fields = profile_fields(req.body)
        aliases = profile_aliases(req.body)
        with req.rw() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT name FROM people WHERE workspace = ? AND id = ?", (req.workspace, id_)
            ).fetchone()
            if not row:
                raise Refused(404, "person not found")
            check_slack(conn, req.workspace, fields["slack_id"], id_)
            for alias in aliases:
                if alias.startswith(people.SLACK):
                    check_slack(conn, req.workspace, alias.removeprefix(people.SLACK), id_)
            aliases = list(dict.fromkeys([a.strip() for a in aliases] + [name]))
            conn.execute(
                "UPDATE people SET name = ?, aliases = ?, slack_id = ?, email = ?, role = ?,"
                " department = ? WHERE workspace = ? AND id = ?",
                (name, json.dumps(aliases), *fields.values(), req.workspace, id_),
            )
            conn.commit()
            return 200, {"id": id_}
    except (ValueError, TypeError):
        return 400, {"error": "invalid id"}
    except Refused as e:
        return e.status, {"error": e.message}


def create(req):
    try:
        body = req.body
        kind = req.params["kind"]
        if kind not in ("item", "person", "project") or not isinstance(body, dict):
            raise Refused(400, "invalid kind")
        title = text(body, "title", 120, True)
        description = text(body, "body")
        at = utc_now_iso()
        with req.rw() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if kind == "person":
                profile = profile_fields(body)
                aliases = profile_aliases(body)
                check_slack(conn, req.workspace, profile["slack_id"])
                for alias in aliases:
                    if alias.startswith(people.SLACK):
                        check_slack(conn, req.workspace, alias.removeprefix(people.SLACK))
                id_ = people.new_person(conn, req.workspace, title)
                conn.execute(
                    "UPDATE people SET slack_id = ?, email = ?, role = ?, department = ?"
                    " WHERE workspace = ? AND id = ?",
                    (*profile.values(), req.workspace, id_),
                )
                for alias in [title, *aliases]:
                    people.add_alias(conn, req.workspace, id_, alias)
            else:
                project = body.get("project_id")
                if (
                    project is not None
                    and not conn.execute(
                        "SELECT 1 FROM tags WHERE workspace = ? AND item_id = ?",
                        (req.workspace, field(body, "project_id", int)),
                    ).fetchone()
                ):
                    raise Refused(404, "tag not found")
                parent = field(body, "parent_id", int, required=False)
                if parent is not None:
                    if (
                        kind != "item"
                        or not conn.execute(
                            "SELECT 1 FROM items WHERE workspace = ? AND id = ?"
                            " AND id NOT IN (SELECT item_id FROM tags)",
                            (req.workspace, parent),
                        ).fetchone()
                    ):
                        raise Refused(404, "parent item not found")
                id_ = conn.execute(
                    "INSERT INTO items"
                    " (workspace, title, body, parent_id, basis, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, 'confirmed', ?, ?)",
                    (
                        req.workspace,
                        title,
                        description,
                        parent,
                        at,
                        at,
                    ),
                ).lastrowid
                if kind == "project":
                    conn.execute(
                        "INSERT INTO tags (item_id, workspace) VALUES (?, ?)", (id_, req.workspace)
                    )
                if project:
                    conn.execute(
                        "INSERT INTO links (workspace, type, from_type, from_id, to_type, to_id,"
                        " created_at) VALUES (?, 'belongs_to', 'record', ?, 'record', ?, ?)",
                        (req.workspace, id_, project, at),
                    )
                conn.execute(
                    "INSERT INTO record_events (workspace, record_id, event, detail, at)"
                    " VALUES (?, ?, 'create', '{}', ?)",
                    (req.workspace, id_, at),
                )
            conn.commit()
            return 200, {"id": id_}
    except Refused as e:
        return e.status, {"error": e.message}


def edit(req):
    try:
        body = req.body
        title = text(body, "title", 120, True)
        description = text(body, "body")
        due = text(body, "due", 100)
        with req.rw() as conn:
            id_ = int(req.params["id"])
            row = conn.execute(
                "SELECT id IN (SELECT item_id FROM tags) FROM items WHERE workspace = ? AND id = ?",
                (req.workspace, id_),
            ).fetchone()
            if not row:
                raise Refused(404, "item not found")
            if row[0]:
                project_actions.rename(conn, req.workspace, id_, title)
            events.append(
                conn, req.workspace, id_, "edit", {"title": title, "body": description, "due": due}
            )
            return 200, {"id": id_}
    except (ValueError, TypeError):
        return 400, {"error": "invalid id"}
    except Refused as e:
        return e.status, {"error": e.message}


ROUTES = [
    Route("POST", "/api/people/<id>/profile", profile),
    Route("GET", "/api/settings", get_settings),
    Route("POST", "/api/settings", save_settings),
    Route("POST", "/api/items/<id>/priority", set_priority),
    Route("POST", "/api/items/<id>/notes", add_note),
    Route("POST", "/api/people/<id>/favorite", favorite_person),
    Route("POST", "/api/tags/<id>", style_tag),
    Route("POST", "/api/create/<kind>", create),
    Route("POST", "/api/records/<id>/edit", edit),
    Route("POST", "/api/items/<id>/edit", edit),
]
