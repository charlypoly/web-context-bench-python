"""Page registry and the network guard that keeps every run offline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit

from wpbench import PAGES_DIR

@dataclass(frozen=True)
class Page:
    id: str
    kind: str
    url: str
    source: str


def load_pages() -> list[Page]:
    data = json.loads((PAGES_DIR / "pages.json").read_text())
    return [Page(**p) for p in data["pages"]]


def pilot_page_ids() -> list[str]:
    return json.loads((PAGES_DIR / "pages.json").read_text())["pilot"]


# Passed to every Chromium the benchmark launches (Playwright's and Stagehand's),
# so no request can leave the machine regardless of which library triggers it.
OFFLINE_ARGS = ["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1"]


def is_local(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme in ("data", "blob", "about", "chrome-extension", "chrome", "devtools"):
        return True
    return parts.hostname in {"localhost", "127.0.0.1", "::1"}


def log_offline_violations(page, blocked: list[str]) -> None:
    """Record every non-local request a page attempts (all of them fail to resolve)."""
    page.on("request", lambda r: None if is_local(r.url) else blocked.append(r.url))
