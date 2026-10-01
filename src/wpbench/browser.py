"""The one way the benchmark launches Chromium through Playwright.

channel="chromium" selects the full Chrome for Testing build bundled with
Playwright rather than chromium-headless-shell, so the browser behaves like
the one Stagehand launches (same binary): new headless mode, site isolation
(cross-site iframes run out of process).
"""

from __future__ import annotations

from wpbench.pages import OFFLINE_ARGS

VIEWPORT = {"width": 1280, "height": 800}


async def launch(playwright, cdp_port: int | None = None):
    args = list(OFFLINE_ARGS)
    if cdp_port is not None:
        args.append(f"--remote-debugging-port={cdp_port}")
    return await playwright.chromium.launch(channel="chromium", headless=True, args=args)


async def new_page(browser):
    ctx = await browser.new_context(viewport=VIEWPORT)
    return ctx, await ctx.new_page()
