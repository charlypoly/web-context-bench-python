"""Capture all six representations of one page, plus the ground truth needed to score them.

One "page session" = one fresh load of the page in the benchmark browser
(raw_html, markdown, accessibility_tree, screenshot, indexed_dom all come from
this load) and one fresh load in Stagehand's own browser (stagehand_snapshot).
Ground truth for every ACT target is resolved in both loads, and every model
answer is later resolved against the same load its representation came from.

Load protocol, identical in both browsers: viewport 1280x800 set before
navigation, goto, wait for network idle, wait 500 ms, scroll position (0, 0).
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import re
from dataclasses import dataclass, field

import markdownify
from playwright.async_api import Page

from wpbench.browser import VIEWPORT
from wpbench.groundtruth import GroundTruthError, ResolvedElement, bounding_box, resolve_chain
from wpbench.workers import Worker

REPRESENTATIONS = ["raw_html", "markdown", "accessibility_tree", "indexed_dom", "stagehand_snapshot", "screenshot"]
SETTLE_MS = 500
# None disables Browser Use's positional cutoff (DomService default: 1000 px past the viewport).
BROWSER_USE_VIEWPORT_THRESHOLD = None


@dataclass
class TargetTruth:
    task_id: str
    main: ResolvedElement | None
    box: dict | None
    stagehand_key: str | None
    stagehand_xpath: str | None
    error: str | None = None


@dataclass
class PageSession:
    page_id: str
    url: str
    page: Page  # live page in the benchmark browser
    cdp: object  # CDP session on that page (top-level target)
    page_target_id: str
    reps: dict[str, object]  # representation name -> text (str) or PNG bytes
    indexed_dom_map: dict[str, dict]
    indexed_dom_meta: dict
    stagehand_xpath_map: dict[str, str]
    stagehand_meta: dict
    truths: dict[str, TargetTruth] = field(default_factory=dict)
    integrity: dict = field(default_factory=dict)


async def _settle(page: Page) -> None:
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(SETTLE_MS)
    await page.evaluate("window.scrollTo(0, 0)")


def stagehand_depth(xpath: str) -> int:
    return len(re.findall(r"/iframe\[\d+\]/html", xpath))


def trim_trailing_text_node(path: str) -> str:
    # Mirrors Stagehand's trimTrailingTextNode (also used inside the adapter).
    return re.sub(r"/text\(\)(\[\d+\])?$", "", path, flags=re.IGNORECASE)


def stagehand_key_for(xpath_map: dict[str, str], el: ResolvedElement, tree: str,
                      frame_prefix: str | None = None) -> tuple[str | None, str | None]:
    """Find the Stagehand encoded id ('<frame ordinal>-<backendNodeId>') of a ground-truth element.

    Stagehand embeds the CDP backendNodeId in the id. Out-of-process frames
    have their own backendNodeId space, so the same number can belong to nodes
    in different frames. Candidates are narrowed by iframe depth and, for
    elements inside an iframe, by the Stagehand xpath of that <iframe> element
    (frame_prefix). Remaining keys must share one xpath (same element); the key
    the formatted tree shows is preferred.
    """
    suffix = f"-{el.backend_node_id}"
    keys = [k for k, xp in xpath_map.items()
            if k.endswith(suffix) and stagehand_depth(xp) == el.frame_depth
            and (frame_prefix is None or xp.startswith(frame_prefix + "/"))]
    xpaths = {trim_trailing_text_node(xpath_map[k]) for k in keys}
    if not keys or len(xpaths) != 1:
        return None, None
    shown = [k for k in keys if f"[{k}]" in tree]
    return (shown or keys)[0], xpaths.pop()


async def stagehand_truth(sh_page, chain: list[str], xpath_map: dict[str, str], tree: str):
    """Resolve a ground-truth chain in Stagehand's browser to its Stagehand id and xpath."""
    el = await resolve_chain(sh_page, chain)
    prefix = None
    if el.frame_depth:
        # The innermost <iframe> on the chain is the last hop that changed frame depth.
        for i in range(len(chain) - 1, 0, -1):
            host = await resolve_chain(sh_page, chain[:i])
            if host.frame_depth == el.frame_depth - 1:
                _, prefix = await stagehand_truth(sh_page, chain[:i], xpath_map, tree)
                break
        if prefix is None:
            return None, None
    return stagehand_key_for(xpath_map, el, tree, prefix)


async def capture_page_session(
    page_id: str,
    url: str,
    act_tasks: list[dict],
    browser,
    cdp_url: str,
    bu: Worker,
    sh: Worker,
    sh_playwright_browser,
) -> PageSession:
    # --- benchmark browser: one load, five representations -----------------
    ctx = await browser.new_context(viewport=VIEWPORT)
    page = await ctx.new_page()
    await page.goto(url)
    await _settle(page)
    session = await ctx.new_cdp_session(page)
    page_target_id = (await session.send("Target.getTargetInfo"))["targetInfo"]["targetId"]

    raw_html = await page.content()
    reps: dict[str, object] = {
        "raw_html": raw_html,
        "markdown": markdownify.markdownify(raw_html),
        "accessibility_tree": await page.locator("body").aria_snapshot(),
        "screenshot": await page.screenshot(type="png"),
    }
    # indexed_dom = Browser Use's own DomService with viewport_threshold=None, so it
    # covers the whole page like the other representations. The agent's default
    # (1000 px past the viewport) is captured too, for the audit only.
    bu_out = await asyncio.to_thread(bu.call, cmd="capture", cdp_url=cdp_url, url=page.url,
                                     viewport_threshold=BROWSER_USE_VIEWPORT_THRESHOLD)
    bu_default = await asyncio.to_thread(bu.call, cmd="capture", cdp_url=cdp_url, url=page.url,
                                         viewport_threshold="agent_default")
    reps["indexed_dom"] = bu_out["text"]
    # Browser Use attached and detached: check it left the page as it was.
    after = await page.content()
    integrity = {
        "raw_html_sha256": hashlib.sha256(raw_html.encode()).hexdigest(),
        "unchanged_after_browser_use": after == raw_html,
        "diff_after_browser_use": None if after == raw_html else "\n".join(
            list(difflib.unified_diff(raw_html.splitlines(), after.splitlines(), lineterm="", n=0))[:40]),
        "scroll_after_browser_use": await page.evaluate("[scrollX, scrollY]"),
    }
    if bu_out["page_target_id"] != page_target_id:
        raise RuntimeError("Browser Use serialized a different tab than the benchmark page")

    # --- Stagehand's own browser: one load, its snapshot ---------------------
    sh_out = await asyncio.to_thread(sh.call, cmd="capture", url=url)
    reps["stagehand_snapshot"] = sh_out["formatted_tree"]
    integrity["stagehand_inner_viewport"] = sh_out["inner_viewport"]
    sh_page = None
    for _ in range(50):  # Playwright's attached view picks up Stagehand's new tab asynchronously
        found = [p for c in sh_playwright_browser.contexts for p in c.pages if p.url == sh_out["url"] and not p.is_closed()]
        if len(found) == 1:
            sh_page = found[0]
            break
        await asyncio.sleep(0.1)
    if sh_page is None:
        raise RuntimeError(f"Stagehand tab for {sh_out['url']} not found exactly once in Playwright's view")

    ps = PageSession(
        page_id=page_id, url=url, page=page, cdp=session, page_target_id=page_target_id, reps=reps,
        indexed_dom_map=bu_out["selector_map"],
        indexed_dom_meta={**{k: bu_out[k] for k in ("config", "agent_would_truncate", "agent_max_chars")},
                          "agent_default_text": bu_default["text"],
                          "agent_default_index_count": len(bu_default["selector_map"]),
                          "index_count": len(bu_out["selector_map"])},
        stagehand_xpath_map=sh_out["xpath_map"],
        stagehand_meta={"url_map": sh_out["url_map"], "inner_viewport": sh_out["inner_viewport"]},
        integrity=integrity,
    )

    # --- ground truth in both loads ------------------------------------------
    # Every target was validated to resolve uniquely (scripts/validate_tasks.py),
    # so a ground-truth failure here is a harness bug: abort rather than score it.
    for task in act_tasks:
        try:
            main_el = await resolve_chain(page, task["target"], page_session=session)
            box = await bounding_box(page, main_el)
            key, xpath = await stagehand_truth(sh_page, task["target"], ps.stagehand_xpath_map, reps["stagehand_snapshot"])
        except GroundTruthError as e:
            raise RuntimeError(f"ground truth failed for {task['id']} on {page_id}: {e}") from e
        if key is None:
            raise RuntimeError(f"no Stagehand id for ground truth of {task['id']} on {page_id}")
        ps.truths[task["id"]] = TargetTruth(task["id"], main_el, box, key, xpath)
    return ps
