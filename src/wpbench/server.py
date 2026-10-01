"""Local static server for snapshots and fixtures. No live sites are contacted.

Each site gets its own port so root-absolute URLs (e.g. /assets/app.js) work.
Servers bind dual-stack, so http://localhost:P and http://127.0.0.1:P both
work; fixtures use the latter as a second, cross-site origin for iframes.
"""

from __future__ import annotations

import mimetypes
import socket
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from wpbench import PAGES_DIR
from wpbench.sitefs import request_to_file


@dataclass(frozen=True)
class Site:
    name: str
    port: int
    directory: Path
    primary_host: str | None  # None: plain static directory (fixtures)


SITES = {
    "fixtures": Site("fixtures", 8100, PAGES_DIR / "fixtures", None),
    "books": Site("books", 8101, PAGES_DIR / "snapshots" / "books", "books.toscrape.com"),
    "saucedemo": Site("saucedemo", 8102, PAGES_DIR / "snapshots" / "saucedemo", "www.saucedemo.com"),
}

# Snapshot files carry no extension when the URL had a query string, so the
# content type captured at snapshot time is stored next to the manifest.
_CONTENT_TYPES: dict[Path, str] = {}


def _load_content_types(site: Site) -> None:
    import json

    manifest = site.directory / "manifest.json"
    if manifest.exists():
        for entry in json.loads(manifest.read_text())["files"]:
            _CONTENT_TYPES[(site.directory / entry["file"]).resolve()] = entry["content_type"]


def _handler(site: Site):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parts = urlsplit(self.path)
            path = unquote(parts.path)
            if site.primary_host is None:
                rel = path.lstrip("/") or "index.html"
                if rel.endswith("/"):
                    rel += "index.html"
                file = (site.directory / rel).resolve()
            else:
                file = request_to_file(site.directory, site.primary_host, path, parts.query).resolve()
            if site.directory.resolve() not in file.parents or not file.is_file():
                self.send_error(404)
                return
            ctype = _CONTENT_TYPES.get(file) or mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            body = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:
            pass

    return Handler


class _DualStackServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6
    daemon_threads = True

    def server_bind(self) -> None:
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


class LocalServers:
    """Context manager running every site server in background threads."""

    def __init__(self, sites: dict[str, Site] = SITES):
        self.sites = sites
        self._servers: list[ThreadingHTTPServer] = []

    def __enter__(self) -> "LocalServers":
        for site in self.sites.values():
            _load_content_types(site)
            srv = _DualStackServer(("::", site.port), _handler(site))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self._servers.append(srv)
        return self

    def __exit__(self, *exc) -> None:
        for srv in self._servers:
            srv.shutdown()
            srv.server_close()


def main() -> None:
    import time

    with LocalServers():
        for s in SITES.values():
            print(f"{s.name}: http://localhost:{s.port}/")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
