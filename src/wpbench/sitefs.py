"""Mapping between URLs and files in a captured snapshot.

Shared by the capture script (writes files) and the local server (reads them),
so both sides agree on where a given URL lives on disk.

Layout of a snapshot site directory:
    <site_dir>/<host>/<path>[__q<sha1(query)[:12]>]
The site's primary host is served at the server root; every other host is
served under /__ext/<host>/... and absolute URLs to it are rewritten to that.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import unquote, urlsplit

EXT_PREFIX = "/__ext/"


def path_to_relfile(host: str, path: str, query: str) -> str:
    if not path or path.endswith("/"):
        path = (path or "/") + "index.html"
    rel = host + path
    if query:
        rel += "__q" + hashlib.sha1(query.encode()).hexdigest()[:12]
    return rel


def url_to_relfile(url: str) -> str:
    parts = urlsplit(url)
    return path_to_relfile(parts.netloc, unquote(parts.path), parts.query)


def request_to_file(site_dir: Path, primary_host: str, path: str, query: str) -> Path:
    """Map a request received by the local server to a file in the snapshot."""
    if path.startswith(EXT_PREFIX):
        host, _, rest = path[len(EXT_PREFIX):].partition("/")
        return site_dir / path_to_relfile(host, "/" + rest, query)
    return site_dir / path_to_relfile(primary_host, path, query)
