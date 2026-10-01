"""Stagehand adapter: runs Stagehand v4's own page snapshot and ref resolution.

Long-lived process speaking JSON lines on stdin/stdout. Stagehand launches
and drives its own Chromium (the same Chrome for Testing binary Playwright
uses, passed as executable_path), because its runtime extension must be
present when the document is created; attached to a page loaded by someone
else, its locators fail ("extension world not ready") and cross-site iframe
content is missing from the snapshot.

Snapshot: Page.snapshot() (stagehand 4.1.0), which calls the same
captureHybridSnapshot that act/observe/extract use, with include_iframes left
at its default (True). The text the model sees is formatted_tree.

Ref resolution follows Stagehand's own act path (normalizeActInferenceElement
in the bundled service worker): xpath = trimTrailingTextNode(xpathMap[ref]),
then a Stagehand locator for "xpath=<xpath>".

Requests:  {"cmd": "launch", "executable_path": "...", "port": 9333, "args": [...]}
           {"cmd": "capture", "url": "..."}
           {"cmd": "resolve", "ref": "0-12"}
           {"cmd": "quit"}
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import traceback
from importlib.metadata import version

_RESPONSES = sys.stdout
sys.stdout = sys.stderr

from stagehand import Stagehand, local_browser  # noqa: E402

VIEWPORT = (1280, 800)


def trim_trailing_text_node(path: str | None) -> str | None:
    # Same regex as Stagehand's trimTrailingTextNode: /\/text\(\)(\[\d+\])?$/iu
    return re.sub(r"/text\(\)(\[\d+\])?$", "", path, flags=re.IGNORECASE) if path else path


class State:
    browser = None
    page = None
    xpath_map: dict[str, str] = {}


async def launch(req: dict) -> dict:
    State.browser = await local_browser.launch(
        headless=True,
        viewport_width=VIEWPORT[0],
        viewport_height=VIEWPORT[1],
        executable_path=req["executable_path"],
        port=req["port"],
        args=req.get("args") or [],
    )
    await Stagehand.create(browser=State.browser)  # no model: snapshot and locators need no LLM
    pages = await State.browser.context.pages()
    State.page = pages[0]
    # local_browser.launch builds its CDP endpoint as http://127.0.0.1:{port} (stagehand/browser.py).
    return {"cdp_url": f"http://127.0.0.1:{req['port']}", "stagehand_version": version("stagehand")}


async def capture(req: dict) -> dict:
    page = State.page
    # launch(viewport_*) only sets the window size; set the page viewport explicitly.
    await page.set_viewport_size(*VIEWPORT)
    await page.goto(req["url"])
    await page.wait_for_load_state("networkidle")
    inner = await page.evaluate("JSON.stringify([innerWidth, innerHeight])")
    snap = (await page.snapshot()).model_dump()
    State.xpath_map = snap["xpath_map"]
    return {
        "formatted_tree": snap["formatted_tree"],
        "xpath_map": snap["xpath_map"],
        "url_map": snap["url_map"],
        "inner_viewport": json.loads(inner),
        "url": await page.url(),
    }


async def resolve(req: dict) -> dict:
    ref = req["ref"]
    raw = State.xpath_map.get(ref)
    if raw is None:
        return {"found": False, "reason": "ref not in xpath_map"}
    xpath = trim_trailing_text_node(raw)
    locator = State.page.locator("xpath=" + xpath)
    count = await locator.count()
    return {"found": True, "xpath": xpath, "count": count}


async def main() -> None:
    loop = asyncio.get_running_loop()
    handlers = {"launch": launch, "capture": capture, "resolve": resolve}
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        req = json.loads(line)
        try:
            if req["cmd"] == "quit":
                _respond({"ok": True})
                break
            result = await handlers[req["cmd"]](req)
            _respond({"ok": True, **result})
        except Exception as e:
            _respond({"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-2000:]})
    if State.browser is not None:
        await State.browser.close()


def _respond(obj: dict) -> None:
    _RESPONSES.write(json.dumps(obj) + "\n")
    _RESPONSES.flush()


if __name__ == "__main__":
    asyncio.run(main())
