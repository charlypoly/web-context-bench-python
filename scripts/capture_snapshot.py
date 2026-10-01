"""Capture a full snapshot (HTML plus every asset the page loads) of practice-site pages.

Run once; the output under pages/snapshots/<site>/ is committed and the
benchmark only ever serves those files locally.

    uv run python scripts/capture_snapshot.py books books.toscrape.com \
        https://books.toscrape.com/ https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html

Documents are stored as the server sent them (not the rendered DOM), so
client-side scripts run again when served locally. Absolute URLs to the
primary host are made root-relative, and URLs to other hosts are rewritten
to /__ext/<host>/..., which the local server maps back to the saved file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
from playwright._repo_version import version as playwright_version

from wpbench import PAGES_DIR
from wpbench.sitefs import EXT_PREFIX, url_to_relfile

TEXT_TYPES = ("text/", "javascript", "json", "xml", "svg", "manifest")


def rewrite(body: str, primary: str, hosts: set[str]) -> str:
    body = re.sub(rf"(https?:)?//{re.escape(primary)}(?=[/\"'?#)\s]|$)", "", body)
    for host in sorted(hosts - {primary}, key=len, reverse=True):
        body = re.sub(rf"(https?:)?//{re.escape(host)}(?=[/\"'?#)\s]|$)", EXT_PREFIX.rstrip("/") + "/" + host, body)
    return body


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("site")
    ap.add_argument("primary_host")
    ap.add_argument("urls", nargs="+")
    args = ap.parse_args()

    out_dir = PAGES_DIR / "snapshots" / args.site
    if out_dir.exists() and any(out_dir.iterdir()):
        sys.exit(f"{out_dir} already exists; refusing to overwrite a committed snapshot")

    responses: dict[str, tuple[str, bytes]] = {}
    failures: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        missing: list[str] = []

        def on_response(resp) -> None:
            if resp.request.method != "GET" or resp.url.startswith("data:"):
                return
            try:
                body = resp.body()
            except Exception:  # body evicted (e.g. after navigation); refetched below
                if resp.status == 200:
                    missing.append(resp.url)
                else:
                    failures.append({"url": resp.url, "status": resp.status})
                return
            if resp.status != 200:
                failures.append({"url": resp.url, "status": resp.status})
                return
            responses[resp.url] = (resp.headers.get("content-type", ""), body)

        for url in args.urls:  # fresh page per URL so bodies are not evicted by navigation
            page = ctx.new_page()
            page.on("response", on_response)
            page.on("requestfailed", lambda r: failures.append({"url": r.url, "error": r.failure}))
            page.goto(url, wait_until="networkidle")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
            page.wait_for_load_state("networkidle")
            page.close()
        for url in missing:
            if url not in responses:
                r = ctx.request.get(url)
                if r.status == 200:
                    responses[url] = (r.headers.get("content-type", ""), r.body())
                else:
                    failures.append({"url": url, "status": r.status, "note": "refetch failed"})
        chromium_version = browser.version
        browser.close()

    hosts = {urlsplit(u).netloc for u in responses}
    files = []
    for url, (ctype, body) in sorted(responses.items()):
        rel = url_to_relfile(url)
        rewritten = False
        if any(t in ctype for t in TEXT_TYPES):
            text = body.decode("utf-8")
            new = rewrite(text, args.primary_host, hosts)
            rewritten = new != text
            data = new.encode("utf-8")
        else:
            data = body
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        files.append({
            "url": url,
            "file": rel,
            "content_type": ctype,
            "sha256_original": hashlib.sha256(body).hexdigest(),
            "sha256_saved": hashlib.sha256(data).hexdigest(),
            "rewritten": rewritten,
        })

    manifest = {
        "site": args.site,
        "primary_host": args.primary_host,
        "source_urls": args.urls,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "captured_with": {"playwright": playwright_version, "chromium": chromium_version},
        "files": files,
        "failed_requests": failures,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"saved {len(files)} files to {out_dir}; {len(failures)} failed requests")
    for f in failures:
        print("  failed:", f)


if __name__ == "__main__":
    main()
