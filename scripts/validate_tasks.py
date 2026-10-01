"""Check tasks.json against the served pages before it is committed.

For every ACT task: the target chain must resolve to exactly one element;
prints its tag, accessible-ish text and box, and the location tag implied by
the box. For every READ task: finds where the answer text appears in the
page (top document, iframes, closed shadow root, attributes) and its
vertical position. Exits non-zero on any resolution failure.
"""

from __future__ import annotations

import asyncio
import json
import sys

from playwright.async_api import async_playwright

from wpbench import ROOT
from wpbench.groundtruth import GroundTruthError, bounding_box, resolve_chain
from wpbench.browser import launch
from wpbench.pages import load_pages
from wpbench.server import LocalServers

VIEWPORT_H = 800


def location_from_box(box) -> str:
    if box is None:
        return "not_rendered"
    bottom = box["y"] + box["height"]
    if bottom <= VIEWPORT_H:
        return "above_fold"
    if box["y"] <= VIEWPORT_H + 1000:
        return "below_fold"
    return "far_below_fold"


async def describe(session, backend_node_id: int) -> str:
    obj = await session.send("DOM.resolveNode", {"backendNodeId": backend_node_id})
    r = await session.send("Runtime.callFunctionOn", {
        "objectId": obj["object"]["objectId"], "returnByValue": True,
        "functionDeclaration": "function(){const t=(this.innerText||this.value||'').trim().slice(0,50);"
                               "return `<${this.tagName.toLowerCase()}> text=${JSON.stringify(t)} aria=${JSON.stringify(this.getAttribute('aria-label'))} ph=${JSON.stringify(this.getAttribute('placeholder'))}`}"})
    return r["result"]["value"]


FIND_TEXT_JS = """(needle) => {
  // Search text nodes, then attribute/form values, across the top document and
  // same-origin frames; closed shadow roots are not reachable from here.
  const hits = [];
  const walk = (doc, where) => {
    const tw = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
    let n; while ((n = tw.nextNode())) {
      if (n.textContent.includes(needle) && n.parentElement && !['SCRIPT','STYLE'].includes(n.parentElement.tagName)) {
        const r = n.parentElement.getBoundingClientRect(); hits.push({where, kind: 'text', y: Math.round(r.top), tag: n.parentElement.tagName});
      }
    }
    for (const el of doc.querySelectorAll('*')) {
      for (const a of el.attributes) if (a.value.includes(needle)) hits.push({where, kind: 'attr:' + a.name, y: Math.round(el.getBoundingClientRect().top), tag: el.tagName});
      if ((el.tagName === 'INPUT' || el.tagName === 'SELECT') && String(el.value).includes(needle)) hits.push({where, kind: 'value', y: Math.round(el.getBoundingClientRect().top), tag: el.tagName});
      if (el.tagName === 'SELECT' && el.selectedOptions[0] && el.selectedOptions[0].text.includes(needle)) hits.push({where, kind: 'selected', y: Math.round(el.getBoundingClientRect().top), tag: el.tagName});
    }
  };
  walk(document, 'top');
  return hits;
}"""


async def main() -> int:
    tasks = json.loads((ROOT / "tasks.json").read_text())["tasks"]
    pages = {p.id: p for p in load_pages()}
    failures = 0
    with LocalServers():
        async with async_playwright() as p:
            browser = await launch(p)
            for page_id, page_def in pages.items():
                ctx = await browser.new_context(viewport={"width": 1280, "height": VIEWPORT_H})
                page = await ctx.new_page()
                await page.goto(page_def.url, wait_until="networkidle")
                print(f"=== {page_id}")
                for t in [t for t in tasks if t["page"] == page_id]:
                    if t["type"] == "act":
                        try:
                            el = await resolve_chain(page, t["target"])
                            box = await bounding_box(page, el)
                            implied = location_from_box(box)
                            if el.frame_depth:
                                implied = "iframe_same_origin" if el.target_id == (await resolve_chain(page, ["body"])).target_id else "iframe_cross_site"
                            if el.in_closed_shadow:
                                implied = "shadow_closed"
                            flag = "" if implied == t["location"] else f"   <-- tagged {t['location']}"
                            print(f"  {t['id']}: {await describe(el.session, el.backend_node_id)} box_y={box and round(box['y'])} implied={implied}{flag}  [hint: {t['target_hint']}]")
                        except GroundTruthError as e:
                            failures += 1
                            print(f"  {t['id']}: FAILED {e}")
                    else:
                        hits = []
                        for f in page.frames:
                            for h in await f.evaluate(FIND_TEXT_JS, t["answer"]):
                                h["where"] = "top" if f == page.main_frame else f"frame:{f.url}"
                                hits.append(h)
                        summary = sorted({(h["where"], h["kind"], h["y"]) for h in hits})[:4]
                        print(f"  {t['id']} [{t['location']}] answer={t['answer']!r}: {summary or 'NOT FOUND in top/frames (closed shadow or derived)'}")
                await ctx.close()
            await browser.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
