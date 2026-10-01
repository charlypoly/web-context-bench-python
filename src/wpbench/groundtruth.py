"""Resolve a ground-truth target (a chain of CSS selectors) to a live element.

The chain crosses boundaries explicitly: every selector except the last must
match an <iframe> (descend into its document) or a shadow host (descend into
its shadow root). Closed shadow roots are reachable only through CDP
(DOM.getDocument with pierce=True), so resolution is done with CDP rather
than Playwright locators, and identity is the CDP backendNodeId.

For a same-process iframe the frame's document is part of the page's DOM
tree; for an out-of-process (cross-site) iframe it lives in a separate CDP
target, reached through a CDP session attached to the Playwright Frame.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class GroundTruthError(Exception):
    pass


@dataclass
class ResolvedElement:
    backend_node_id: int
    # CDP target that owns the node: the page target, or the OOPIF target.
    target_id: str
    # Number of iframe boundaries crossed (0 = top document).
    frame_depth: int
    in_closed_shadow: bool
    in_shadow: bool
    chain: list[str]
    session: object = field(repr=False, default=None)
    playwright_frame: object = field(repr=False, default=None)


def _index_tree(node: dict, by_id: dict[int, dict]) -> None:
    by_id[node["nodeId"]] = node
    for key in ("children", "shadowRoots", "pseudoElements"):
        for child in node.get(key, []):
            _index_tree(child, by_id)
    if "contentDocument" in node:
        _index_tree(node["contentDocument"], by_id)
    if "templateContent" in node:
        _index_tree(node["templateContent"], by_id)


async def _target_id(session) -> str:
    info = await session.send("Target.getTargetInfo")
    return info["targetInfo"]["targetId"]


async def _query_unique(session, scope_node_id: int, selector: str) -> int:
    res = await session.send("DOM.querySelectorAll", {"nodeId": scope_node_id, "selector": selector})
    ids = res["nodeIds"]
    if len(ids) != 1:
        raise GroundTruthError(f"selector {selector!r} matched {len(ids)} elements (expected exactly 1)")
    return ids[0]


async def resolve_chain(page, chain: list[str], page_session=None) -> ResolvedElement:
    """Resolve `chain` in a Playwright page. `page_session` may be passed to reuse a CDP session."""
    context = page.context
    session = page_session or await context.new_cdp_session(page)
    target_id = await _target_id(session)
    frame = page.main_frame
    doc = await session.send("DOM.getDocument", {"depth": -1, "pierce": True})
    by_id: dict[int, dict] = {}
    _index_tree(doc["root"], by_id)
    scope = doc["root"]["nodeId"]
    frame_depth = 0
    in_shadow = in_closed = False

    for i, selector in enumerate(chain):
        node_id = await _query_unique(session, scope, selector)
        if i == len(chain) - 1:
            desc = await session.send("DOM.describeNode", {"nodeId": node_id})
            return ResolvedElement(
                backend_node_id=desc["node"]["backendNodeId"],
                target_id=target_id,
                frame_depth=frame_depth,
                in_closed_shadow=in_closed,
                in_shadow=in_shadow,
                chain=chain,
                session=session,
                playwright_frame=frame,
            )
        node = by_id.get(node_id)
        if node is None:
            raise GroundTruthError(f"node for {selector!r} missing from pierced document")
        if node.get("localName") == "iframe":
            frame_depth += 1
            child_frame = await _child_playwright_frame(frame, node)
            if "contentDocument" in node:  # same-process frame: already in this tree
                scope = node["contentDocument"]["nodeId"]
            else:  # out-of-process frame: separate CDP target
                session = await context.new_cdp_session(child_frame)
                target_id = await _target_id(session)
                sub = await session.send("DOM.getDocument", {"depth": -1, "pierce": True})
                by_id = {}
                _index_tree(sub["root"], by_id)
                scope = sub["root"]["nodeId"]
            frame = child_frame
        elif node.get("shadowRoots"):
            root = node["shadowRoots"][0]
            in_shadow = True
            in_closed = in_closed or root.get("shadowRootType") == "closed"
            scope = root["nodeId"]
        else:
            raise GroundTruthError(f"{selector!r} is neither an iframe nor a shadow host")
    raise GroundTruthError("empty chain")


async def _child_playwright_frame(parent_frame, iframe_node: dict):
    """Find the Playwright Frame for an <iframe> node, matched by its id/name/src attributes."""
    attrs = dict(zip(iframe_node.get("attributes", [])[::2], iframe_node.get("attributes", [])[1::2]))
    candidates = [f for f in parent_frame.child_frames if not f.is_detached()]
    for f in candidates:
        try:
            el = await f.frame_element()
        except Exception:  # detached between listing and lookup
            continue
        same = await el.evaluate(
            "(e, a) => (a.id ? e.id === a.id : true) && (a.src ? e.getAttribute('src') === a.src : true)",
            {"id": attrs.get("id"), "src": attrs.get("src")},
        )
        if same:
            return f
    raise GroundTruthError(f"no Playwright frame for iframe {attrs}")


async def bounding_box(page, el: ResolvedElement) -> dict | None:
    """Border box of the element in top-level viewport CSS pixels ({x, y, width, height}).

    Targets outside shadow roots use Playwright, which maps boxes from any
    iframe (including out-of-process ones) to top-level viewport coordinates.
    Closed-shadow targets are unreachable for Playwright, so their box comes
    from CDP DOM.getBoxModel, which is in top-level viewport coordinates for
    nodes of the top-level document.
    """
    if not el.in_shadow:
        loc = page.locator(el.chain[0])
        for selector in el.chain[1:]:
            loc = loc.content_frame.locator(selector)
        return await loc.bounding_box()
    if el.frame_depth:
        raise GroundTruthError("shadow-root targets inside iframes are not supported")
    try:
        model = await el.session.send("DOM.getBoxModel", {"backendNodeId": el.backend_node_id})
    except Exception:
        return None  # not rendered
    q = model["model"]["border"]
    xs, ys = q[0::2], q[1::2]
    return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}
