"""Regression test: concurrent raw_html resolutions on one page session must not interfere.

The full run's first attempt scored 2 valid selectors as invalid_selector
because concurrent resolutions shared one CDP session (DOM.getDocument resets
node ids). Runs the raw_html resolver 40x concurrently with oracle selectors.
"""

import asyncio
import json

from playwright.async_api import async_playwright

from wpbench import ROOT
from wpbench.harness import Harness
from wpbench.resolve import resolve_act


def test_concurrent_raw_html_resolution():
    async def run():
        tasks = [t for t in json.loads((ROOT / "tasks.json").read_text())["tasks"]
                 if t["page"] == "books_product" and t["type"] == "act"]
        async with async_playwright() as p:
            async with Harness(p) as h:
                ps = await h.capture("books_product", tasks)
                calls = [resolve_act("raw_html", ps, t["id"], {"selector": t["target"][0]}, None)
                         for t in tasks for _ in range(40)]
                results = await asyncio.gather(*calls)
                await ps.page.context.close()
                return results

    results = asyncio.run(run())
    assert all(r.correct for r in results), [r.reason for r in results if not r.correct][:5]
