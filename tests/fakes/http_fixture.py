#!/usr/bin/env python3
"""Fixture-routed HTTP driver for stdlib CLIs (stdlib only, CLI-agnostic).

Usage:
  python3 http_fixture.py CLI.py ROUTES.json [--log FILE] -- ARGS...

Loads CLI.py by path (as module ``__fixture_cli__``, so its ``if __name__ == "__main__"``
block does not run), sets ``sys.argv = [CLI.py, *ARGS]``, replaces
``urllib.request.urlopen`` with a router over ROUTES.json and calls the module's ``main()``.
The driver's exit code is the CLI's. Nothing leaves the machine: no route for a request
exits 3, and ``socket.create_connection`` raises. ``time.sleep`` is a no-op so retry paths
run instantly.

The CLI must call ``urllib.request.urlopen(...)`` fully qualified (a ``from urllib.request
import urlopen`` taken at import time would bypass the router) and expose ``main()``.

Routes file: a JSON list (or ``{"routes": [...]}``) of objects, tried in order; the first
route whose ``method`` and ``url`` match answers:

  method   HTTP method to match ("GET", "POST", ...); omitted = any method
  url      regular expression, ``re.search``-ed against the full request URL
  status   HTTP status (default 200); a non-2xx status raises ``urllib.error.HTTPError``
           with the body as its payload, so the CLI's own error mapping runs
  body     response body: a string is sent as is, anything else as JSON
  headers  optional response headers ({"Content-Type": "..."})
  once     true = the route answers one request and is then skipped (e.g. a 429 followed
           by a 200 from the next matching route)
  error    a string: raise ``urllib.error.URLError(error)`` instead (unreachable host)

Observability (never header values, never credentials):
  stderr   ``>> METHOD URL [BODY]`` per request; BODY is the request body cut to 200
           characters, with the values of form or JSON keys that look like credentials
           (token, secret, password, verifier, code) replaced by REDACTED
  --log    one line ``METHOD URL auth=yes|no`` per request, appended to FILE; ``auth``
           says whether an Authorization header was sent
"""
import importlib.util
import io
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message

SECRET_KEY_RE = re.compile(r"token|secret|password|verifier|^code$", re.I)


def _usage(msg):
    print(f"http_fixture: {msg}\nusage: http_fixture.py CLI.py ROUTES.json [--log FILE] -- ARGS...",
          file=sys.stderr)
    sys.exit(64)


def _redact_body(data):
    if data is None:
        return ""
    if isinstance(data, (bytes, bytearray)):
        text = bytes(data).decode("utf-8", "replace")
    else:
        text = str(data)
    try:
        obj = json.loads(text)
    except ValueError:
        obj = None
    if isinstance(obj, dict):
        obj = {k: ("REDACTED" if SECRET_KEY_RE.search(k) else v) for k, v in obj.items()}
        text = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    elif "=" in text and "\n" not in text and " " not in text:
        pairs = urllib.parse.parse_qsl(text, keep_blank_values=True)
        if pairs:
            text = "&".join(f"{k}={'REDACTED' if SECRET_KEY_RE.search(k) else v}" for k, v in pairs)
    return text[:200]


class _Response(io.BytesIO):
    def __init__(self, url, status, body, headers):
        super().__init__(body)
        self.url, self.status, self.code = url, status, status
        self.headers = Message()
        for k, v in (headers or {}).items():
            self.headers[k] = v

    def getcode(self):
        return self.status

    def info(self):
        return self.headers

    def geturl(self):
        return self.url


class Router:
    def __init__(self, routes, log):
        self.routes = routes
        self.used = set()
        self.log = log

    def __call__(self, request, data=None, timeout=None, **_kw):
        if isinstance(request, str):
            request = urllib.request.Request(request, data=data)
        method = request.get_method()
        url = request.full_url
        authed = bool(request.get_header("Authorization"))
        body = _redact_body(request.data)
        print(f">> {method} {url}{' ' + body if body else ''}", file=sys.stderr)
        if self.log:
            with open(self.log, "a") as fh:
                fh.write(f"{method} {url} auth={'yes' if authed else 'no'}\n")
        for i, r in enumerate(self.routes):
            if i in self.used:
                continue
            if r.get("method") and r["method"].upper() != method:
                continue
            if not re.search(r.get("url", ""), url):
                continue
            if r.get("once"):
                self.used.add(i)
            if r.get("error"):
                raise urllib.error.URLError(r["error"])
            status = int(r.get("status", 200))
            raw = r.get("body", "")
            payload = (raw if isinstance(raw, str) else json.dumps(raw)).encode()
            headers = r.get("headers") or {}
            if not 200 <= status < 300:
                hdrs = Message()
                for k, v in headers.items():
                    hdrs[k] = v
                raise urllib.error.HTTPError(url, status, f"fixture {status}", hdrs, io.BytesIO(payload))
            return _Response(url, status, payload, headers)
        sys.stdout.flush()
        print(f"http_fixture: no route for {method} {url}", file=sys.stderr)
        sys.exit(3)


def _no_network(*_a, **_kw):
    raise OSError("http_fixture: network access is disabled")


def main():
    argv = sys.argv[1:]
    if "--" not in argv:
        _usage("missing -- before the CLI arguments")
    split = argv.index("--")
    head, args = argv[:split], argv[split + 1:]
    log = None
    if "--log" in head:
        i = head.index("--log")
        if i + 1 >= len(head):
            _usage("--log needs a FILE")
        log = head[i + 1]
        head = head[:i] + head[i + 2:]
    if len(head) != 2:
        _usage("need CLI.py and ROUTES.json")
    cli, routes_path = head
    with open(routes_path) as fh:
        routes = json.load(fh)
    if isinstance(routes, dict):
        routes = routes.get("routes", [])
    if not isinstance(routes, list):
        _usage(f"{routes_path}: expected a list of routes")

    urllib.request.urlopen = Router(routes, log)
    socket.create_connection = _no_network
    time.sleep = lambda *_a, **_kw: None

    sys.argv = [cli] + args
    spec = importlib.util.spec_from_file_location("__fixture_cli__", os.path.abspath(cli))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["__fixture_cli__"] = mod
    spec.loader.exec_module(mod)
    if not callable(getattr(mod, "main", None)):
        _usage(f"{cli} has no main()")
    try:
        mod.main()
    finally:
        sys.stdout.flush()


if __name__ == "__main__":
    main()
