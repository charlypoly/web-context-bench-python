"""Resolve a model's ACT answer to a live element and compare it with ground truth.

Every resolver returns an ActResult. `correct` is True only when the answer
resolves to exactly the ground-truth element. `reason` names why not.
Element identity in the benchmark browser is (CDP target id, backendNodeId);
in Stagehand's browser it is Stagehand's own xpath for the element.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass

from wpbench.capture import PageSession, TargetTruth

# Roles tried, in this order of precedence, when resolving a Markdown text answer.
MARKDOWN_ROLES = ["button", "link", "textbox", "searchbox", "checkbox", "radio", "combobox", "listbox",
                  "option", "menuitem", "tab", "switch", "spinbutton", "slider"]


@dataclass
class ActResult:
    correct: bool
    reason: str  # "correct" or a failure reason
    resolved: dict | None = None  # what the answer resolved to, for the audit log

    def to_dict(self) -> dict:
        return asdict(self)


def _fail(reason: str, resolved: dict | None = None) -> ActResult:
    return ActResult(False, reason, resolved)


async def _describe_handle(handle) -> dict:
    return await handle.evaluate(
        "e => ({tag: e.tagName.toLowerCase(), id: e.id || null, text: (e.innerText || e.value || '').trim().slice(0, 80),"
        " outer: e.outerHTML.slice(0, 200)})")


async def _describe_backend(session, backend_node_id: int) -> dict:
    obj = await session.send("DOM.resolveNode", {"backendNodeId": backend_node_id})
    r = await session.send("Runtime.callFunctionOn", {
        "objectId": obj["object"]["objectId"], "returnByValue": True,
        "functionDeclaration": "function(){return {tag: this.tagName ? this.tagName.toLowerCase() : this.nodeName,"
                               " text: ((this.innerText || this.value || this.textContent || '') + '').trim().slice(0, 80),"
                               " outer: (this.outerHTML || '').slice(0, 200)}}"})
    return r["result"]["value"]


async def _same_as_truth_handle(ps: PageSession, truth: TargetTruth, handle) -> bool:
    """Is a Playwright handle (always in the top document) the ground-truth element?"""
    if truth.main.frame_depth or truth.main.in_shadow:
        return False  # top-document handles cannot be inside iframes or shadow roots
    gt = await ps.page.locator(truth.main.chain[0]).element_handle()
    return await ps.page.evaluate("([a, b]) => a === b", [handle, gt])


def _occurrence(answer: dict) -> tuple[int | None, str | None]:
    occ = answer.get("occurrence")
    if occ is None:
        return None, None
    if isinstance(occ, bool) or not isinstance(occ, int) or occ < 1:
        return None, "invalid_occurrence"
    return occ, None


async def _pick(locator, answer: dict) -> tuple[object | None, str | None, int]:
    count = await locator.count()
    if count == 0:
        return None, "no_match", 0
    occ, err = _occurrence(answer)
    if err:
        return None, err, count
    if occ is None:
        if count > 1:
            return None, "ambiguous", count
        occ = 1
    if occ > count:
        return None, "occurrence_out_of_range", count
    return await locator.nth(occ - 1).element_handle(), None, count


# --- one resolver per representation -------------------------------------------

async def resolve_raw_html(ps: PageSession, truth: TargetTruth, answer: dict) -> ActResult:
    selector = answer.get("selector")
    if not isinstance(selector, str) or not selector.strip():
        return _fail("malformed_answer")
    session = ps.cdp
    doc = await session.send("DOM.getDocument", {"depth": 0})
    try:
        res = await session.send("DOM.querySelectorAll", {"nodeId": doc["root"]["nodeId"], "selector": selector})
    except Exception:
        return _fail("invalid_selector", {"selector": selector})
    ids = res["nodeIds"]
    if not ids:
        return _fail("no_match", {"selector": selector})
    if len(ids) > 1:
        return _fail("ambiguous", {"selector": selector, "matches": len(ids)})
    desc = await session.send("DOM.describeNode", {"nodeId": ids[0]})
    bnid = desc["node"]["backendNodeId"]
    resolved = {"selector": selector, "backend_node_id": bnid, **await _describe_backend(session, bnid)}
    ok = truth.main.target_id == ps.page_target_id and truth.main.backend_node_id == bnid
    return ActResult(ok, "correct" if ok else "wrong_element", resolved)


async def resolve_markdown(ps: PageSession, truth: TargetTruth, answer: dict) -> ActResult:
    text = answer.get("text")
    if not isinstance(text, str) or not text.strip():
        return _fail("malformed_answer")
    text = text.strip()
    page = ps.page
    by_role = None
    for role in MARKDOWN_ROLES:
        loc = page.get_by_role(role, name=text, exact=True)
        by_role = loc if by_role is None else by_role.or_(loc)
    strategies = [
        ("role_name", by_role),
        ("label", page.get_by_label(text, exact=True)),
        ("placeholder", page.get_by_placeholder(text, exact=True)),
        ("text", page.get_by_text(text, exact=True)),
    ]
    for name, loc in strategies:
        if await loc.count() == 0:
            continue
        handle, err, count = await _pick(loc, answer)
        if err:
            return _fail(err, {"strategy": name, "text": text, "matches": count})
        resolved = {"strategy": name, "text": text, "matches": count, **await _describe_handle(handle)}
        ok = await _same_as_truth_handle(ps, truth, handle)
        return ActResult(ok, "correct" if ok else "wrong_element", resolved)
    return _fail("no_match", {"text": text})


async def resolve_accessibility_tree(ps: PageSession, truth: TargetTruth, answer: dict) -> ActResult:
    role, name = answer.get("role"), answer.get("name")
    if not isinstance(role, str) or not role.strip() or (name is not None and not isinstance(name, str)):
        return _fail("malformed_answer")
    try:
        loc = ps.page.get_by_role(role.strip(), name=name, exact=True) if name else ps.page.get_by_role(role.strip())
        await loc.count()
    except Exception:
        return _fail("invalid_role", {"role": role, "name": name})
    handle, err, count = await _pick(loc, answer)
    if err:
        return _fail(err, {"role": role, "name": name, "matches": count})
    resolved = {"role": role, "name": name, "matches": count, **await _describe_handle(handle)}
    ok = await _same_as_truth_handle(ps, truth, handle)
    return ActResult(ok, "correct" if ok else "wrong_element", resolved)


async def resolve_indexed_dom(ps: PageSession, truth: TargetTruth, answer: dict) -> ActResult:
    index = answer.get("index")
    if isinstance(index, str) and index.strip().isdigit():
        index = int(index.strip())
    if isinstance(index, bool) or not isinstance(index, int):
        return _fail("malformed_answer")
    node = ps.indexed_dom_map.get(str(index))
    if node is None:
        return _fail("unknown_index", {"index": index})
    resolved = {"index": index, "backend_node_id": node["backend_node_id"], "node_name": node["node_name"],
                "attributes": node["attributes"]}
    ok = (node["target_id"], node["backend_node_id"]) == (truth.main.target_id, truth.main.backend_node_id)
    return ActResult(ok, "correct" if ok else "wrong_element", resolved)


async def resolve_stagehand_snapshot(ps: PageSession, truth: TargetTruth, answer: dict, sh_worker) -> ActResult:
    ref = answer.get("ref")
    if not isinstance(ref, str) or not ref.strip():
        return _fail("malformed_answer")
    ref = ref.strip().strip("[]")
    out = await asyncio.to_thread(sh_worker.call, cmd="resolve", ref=ref)
    if not out["found"]:
        return _fail("unknown_ref", {"ref": ref})
    resolved = {"ref": ref, "xpath": out["xpath"], "matches": out["count"]}
    if out["count"] == 0:
        return _fail("no_match", resolved)
    if out["count"] > 1:
        return _fail("ambiguous", resolved)
    if truth.stagehand_xpath is None:
        return _fail("ground_truth_missing_in_stagehand", resolved)
    ok = out["xpath"] == truth.stagehand_xpath
    return ActResult(ok, "correct" if ok else "wrong_element", resolved)


async def resolve_screenshot(ps: PageSession, truth: TargetTruth, answer: dict) -> ActResult:
    x, y = answer.get("x"), answer.get("y")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (x, y)):
        return _fail("malformed_answer")
    box = truth.box
    resolved = {"x": x, "y": y, "target_box": box}
    # Record what is actually at that point, for the audit log only.
    try:
        session = ps.cdp
        hit = await session.send("DOM.getNodeForLocation", {"x": int(x), "y": int(y), "includeUserAgentShadowDOM": False})
        resolved["element_at_point"] = await _describe_backend(session, hit["backendNodeId"])
    except Exception:
        resolved["element_at_point"] = None
    if not (0 <= x < 1280 and 0 <= y < 800):
        return _fail("outside_screenshot", resolved)
    if box is None:
        return _fail("target_not_rendered", resolved)
    inside = box["x"] <= x <= box["x"] + box["width"] and box["y"] <= y <= box["y"] + box["height"]
    return ActResult(inside, "correct" if inside else "outside_target_box", resolved)


async def resolve_act(rep: str, ps: PageSession, task_id: str, answer: dict | None, sh_worker) -> ActResult:
    truth = ps.truths[task_id]
    if truth.main is None:
        return _fail("ground_truth_error:" + (truth.error or ""))
    if not isinstance(answer, dict) or answer.get("answer", "absent") is None and len(answer) == 1:
        return _fail("no_answer")
    if rep == "raw_html":
        return await resolve_raw_html(ps, truth, answer)
    if rep == "markdown":
        return await resolve_markdown(ps, truth, answer)
    if rep == "accessibility_tree":
        return await resolve_accessibility_tree(ps, truth, answer)
    if rep == "indexed_dom":
        return await resolve_indexed_dom(ps, truth, answer)
    if rep == "stagehand_snapshot":
        return await resolve_stagehand_snapshot(ps, truth, answer, sh_worker)
    if rep == "screenshot":
        return await resolve_screenshot(ps, truth, answer)
    raise ValueError(rep)
