"""Render every page from the local server, offline, and report problems.

Prints non-local requests (blocked by OFFLINE_ARGS), failed and non-200
requests, and saves a full-page screenshot per page to results/tmp/verify/.
"""

from __future__ import annotations

import asyncio

from playwright.async_api import async_playwright

from wpbench import RESULTS_DIR
from wpbench.pages import OFFLINE_ARGS, load_pages, log_offline_violations
from wpbench.server import LocalServers


async def main() -> None:
    out = RESULTS_DIR / "tmp" / "verify"
    out.mkdir(parents=True, exist_ok=True)
    with LocalServers():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=OFFLINE_ARGS)
            for pg in load_pages():
                ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
                page = await ctx.new_page()
                blocked, bad = [], []
                log_offline_violations(page, blocked)
                page.on("response", lambda r: r.status >= 400 and bad.append(f"{r.status} {r.url}"))
                page.on("requestfailed", lambda r: bad.append(f"FAILED {r.url} {r.failure}"))
                try:
                    resp = await page.goto(pg.url, wait_until="networkidle")
                    status = resp.status if resp else None
                except Exception as e:
                    status = f"ERROR {e}"
                if status == 200:
                    await page.screenshot(path=out / f"{pg.id}.png", full_page=True)
                print(f"{pg.id}: status={status} blocked={len(blocked)} problems={len(bad)}")
                for u in sorted(set(blocked)):
                    print("   blocked:", u)
                for b in sorted(set(bad)):
                    print("   ", b)
                await ctx.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
