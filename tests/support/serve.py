"""A `librarian serve` subprocess and an HTTP client for it."""

import http.client
import os
import re
import subprocess
import sys


class Served:
    def __init__(self, proc, port, home):
        self.proc, self.port, self.home = proc, port, home

    def request(self, method, path, headers=None, body=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": host or f"127.0.0.1:{self.port}", **(headers or {})}
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode()
        conn.close()
        return resp, data

    def token(self):
        _, page = self.request("GET", "/")
        return re.search(r'name="librarian-token" content="([^"]+)"', page).group(1)


def spawn(home, *args, env=None):
    proc = subprocess.Popen(
        [sys.executable, "-m", "librarian", "serve", *args],
        env={**os.environ, "LIBRARIAN_HOME": str(home), **(env or {})},
        stdout=subprocess.PIPE,
        text=True,
    )
    port = int(re.search(r":(\d+)/", proc.stdout.readline()).group(1))
    return proc, Served(proc, port, home)
