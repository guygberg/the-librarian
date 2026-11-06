import json
import sqlite3

from support.cli import run_librarian
from support.recordings import run_import


class Api:
    """A served workspace driven over HTTP, with the CLI and the database beside it for checking."""

    def __init__(self, served, home, env):
        self.served, self.home, self.env = served, home, env
        self.headers = {"Content-Type": "application/json", "X-Librarian-Token": served.token()}

    def call(self, method, path, body=None, headers=None):
        resp, data = self.served.request(method, path, headers or self.headers, json.dumps(body) if body else None)
        return resp.status, json.loads(data)

    def post(self, path, body=None, headers=None):
        return self.call("POST", path, body or {}, headers)

    def review(self):
        return self.call("GET", "/api/review")[1]

    def conn(self):
        return sqlite3.connect(next(self.home.rglob("*.db")))

    def sql(self, query, *params):
        return self.conn().execute(query, params).fetchall()

    def record(self, title):
        return self.sql("SELECT id FROM records WHERE title = ?", title)[0][0]

    def person(self, name):
        return self.sql("SELECT id FROM persons WHERE name = ?", name)[0][0]

    def row(self, title):
        [row] = [r for r in self.review()["rows"] if r["record"]["title"] == title]
        return row

    def cli(self, *args, **env):
        out = run_librarian(list(args), self.home, env={**self.env, **env})
        assert out.returncode == 0, out.stdout
        return json.loads(out.stdout)

    def show(self, title):
        return self.cli("show", str(self.record(title)))

    def open_items(self):
        return {r["title"]: r["group"] for r in self.cli("open-items", TZ="UTC")["records"]}

    def reimport(self):
        code, out = run_import(self.home, self.env)
        assert code == 0, out

    def events(self, name):
        return [e for (e,) in self.sql("SELECT event FROM record_events WHERE event = ?", name)]
