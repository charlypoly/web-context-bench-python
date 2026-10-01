"""Browser Use adapter: runs Browser Use's own DOM serializer, nothing else.

Long-lived process speaking JSON lines on stdin/stdout. It attaches over CDP
to the benchmark's Chromium (it never launches or navigates a browser) and
returns exactly what the Browser Use agent would put in its prompt.

Path used (browser-use 0.13.10), identical to the agent's:
  BrowserSession.get_browser_state_summary()   -> DOMWatchdog -> DomService(
      cross_origin_iframes, paint_order_filtering, max_iframes, max_iframe_depth
      from the default BrowserProfile; viewport_threshold left at DomService's default)
  SerializedDOMState.llm_representation(include_attributes=DEFAULT_INCLUDE_ATTRIBUTES)
      (agent/prompts.py calls it this way, then truncates to
       max_clickable_elements_length=40000 characters; we return the
       untruncated text and report whether the agent would have truncated it)

Requests:  {"cmd": "capture", "cdp_url": "...", "url": "..."}
           {"cmd": "quit"}
Responses: {"ok": true, ...} or {"ok": false, "error": "..."}
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from importlib.metadata import version

# Responses go to the real stdout; everything the library prints goes to stderr.
_RESPONSES = sys.stdout
sys.stdout = sys.stderr

os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("BROWSER_USE_CLOUD_SYNC", "false")
os.environ.setdefault("BROWSER_USE_LOGGING_LEVEL", "error")

from browser_use import BrowserSession  # noqa: E402
from browser_use.agent.prompts import AgentMessagePrompt  # noqa: E402
from browser_use.browser.events import SwitchTabEvent  # noqa: E402
from browser_use.dom.views import DEFAULT_INCLUDE_ATTRIBUTES  # noqa: E402

def _agent_max_chars() -> int:
    import inspect

    return inspect.signature(AgentMessagePrompt.__init__).parameters["max_clickable_elements_length"].default


async def capture(cdp_url: str, url: str) -> dict:
    session = BrowserSession(cdp_url=cdp_url, highlight_elements=False)
    await session.start()
    try:
        tabs = await session.get_tabs()
        matches = [t.target_id for t in tabs if t.url == url]
        if len(matches) != 1:
            raise RuntimeError(f"expected exactly one tab at {url}, found {[t.url for t in tabs]}")
        page_target = matches[0]
        await session.event_bus.dispatch(SwitchTabEvent(target_id=page_target))
        state = await session.get_browser_state_summary(include_screenshot=False)
        dom = state.dom_state
        text = dom.llm_representation(include_attributes=DEFAULT_INCLUDE_ATTRIBUTES)
        selector_map = {
            str(index): {
                "backend_node_id": node.backend_node_id,
                "target_id": node.target_id,
                "node_name": node.node_name,
                "attributes": node.attributes,
                "xpath": node.xpath,
            }
            for index, node in dom.selector_map.items()
        }
        profile = session.browser_profile
        max_chars = _agent_max_chars()
        return {
            "text": text,
            "selector_map": selector_map,
            "page_target_id": page_target,
            "agent_would_truncate": len(text) > max_chars,
            "agent_max_chars": max_chars,
            "config": {
                "browser_use_version": version("browser-use"),
                "cross_origin_iframes": profile.cross_origin_iframes,
                "paint_order_filtering": profile.paint_order_filtering,
                "max_iframes": profile.max_iframes,
                "max_iframe_depth": profile.max_iframe_depth,
                "include_attributes": DEFAULT_INCLUDE_ATTRIBUTES,
            },
        }
    finally:
        await session.stop()  # detaches; the benchmark's browser keeps running


def _respond(obj: dict) -> None:
    _RESPONSES.write(json.dumps(obj) + "\n")
    _RESPONSES.flush()


async def main() -> None:
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            return
        req = json.loads(line)
        try:
            if req["cmd"] == "quit":
                _respond({"ok": True})
                return
            if req["cmd"] == "capture":
                result = await capture(req["cdp_url"], req["url"])
                _respond({"ok": True, **result})
            else:
                raise ValueError(f"unknown cmd {req['cmd']!r}")
        except Exception as e:
            _respond({"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-2000:]})


if __name__ == "__main__":
    asyncio.run(main())
