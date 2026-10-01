"""Offline self-test of answer resolution and representability (no API calls).

For every ACT task on the selected pages and every representation, builds the
answer a perfect model would give from ground truth (the "oracle" answer) and
checks that the resolver scores it correct exactly when the representability
check says the target is present. Also checks that a wrong answer (another
task's target on the same page) is scored incorrect.

    uv run python scripts/selftest_resolution.py [page_id ...]
"""

from __future__ import annotations

import asyncio
import json
import sys

from playwright.async_api import async_playwright

from wpbench import ROOT
from wpbench.capture import REPRESENTATIONS
from wpbench.harness import Harness
from wpbench.resolve import resolve_act
from wpbench.scoring import NON_ROLE_KEYS, _target_strings, act_target_representable, normalize, parse_aria_line


async def oracle(rep, ps, task, truth):
    """The answer a perfect model would give, or None if it cannot be expressed."""
    if rep == "raw_html":
        return {"selector": truth.main.chain[0]} if len(truth.main.chain) == 1 else None
    if rep == "indexed_dom":
        for idx, n in ps.indexed_dom_map.items():
            if (n["target_id"], n["backend_node_id"]) == (truth.main.target_id, truth.main.backend_node_id):
                return {"index": int(idx)}
        return None
    if rep == "stagehand_snapshot":
        return {"ref": truth.stagehand_key} if truth.stagehand_key else None
    if rep == "screenshot":
        b = truth.box
        return {"x": round(b["x"] + b["width"] / 2), "y": round(b["y"] + b["height"] / 2)} if b else None
    if truth.main.frame_depth or truth.main.in_shadow:
        return None
    if rep == "markdown":
        md = normalize(ps.reps["markdown"])
        for s in await _target_strings(ps, truth):
            if normalize(s) in md:
                for occ in range(1, 40):
                    r = await resolve_act(rep, ps, task["id"], {"text": s.strip(), "occurrence": occ}, None)
                    if r.correct:
                        return {"text": s.strip(), "occurrence": occ}
                    if r.reason in ("occurrence_out_of_range", "no_match"):
                        break
        return None
    if rep == "accessibility_tree":
        own = await ps.page.locator(truth.main.chain[0]).aria_snapshot()
        node = parse_aria_line(own.splitlines()[0]) if own.strip() else None
        if node is None or node[0] in NON_ROLE_KEYS:
            return None
        for occ in range(1, 40):
            ans = {"role": node[0], "name": node[1], "occurrence": occ}
            r = await resolve_act(rep, ps, task["id"], ans, None)
            if r.correct:
                return ans
            if r.reason in ("occurrence_out_of_range", "no_match"):
                break
        return None


async def main(page_ids: list[str]) -> int:
    tasks = json.loads((ROOT / "tasks.json").read_text())["tasks"]
    problems = 0
    async with async_playwright() as p:
        async with Harness(p) as h:
            for page_id in page_ids:
                act = [t for t in tasks if t["page"] == page_id and t["type"] == "act"]
                ps = await h.capture(page_id, act)
                print(f"=== {page_id}  integrity={ps.integrity}")
                for i, task in enumerate(act):
                    truth = ps.truths[task["id"]]
                    other = act[(i + 1) % len(act)]
                    for rep in REPRESENTATIONS:
                        representable, why = await act_target_representable(rep, ps, task["id"])
                        ans = await oracle(rep, ps, task, truth)
                        res = await resolve_act(rep, ps, task["id"], ans, h.sh) if ans else None
                        ok = bool(res and res.correct)
                        # wrong answer: the oracle answer for a different target must not score
                        wrong_ans = await oracle(rep, ps, other, ps.truths[other["id"]])
                        wrong = await resolve_act(rep, ps, task["id"], wrong_ans, h.sh) if wrong_ans else None
                        wrong_ok = not (wrong and wrong.correct)
                        flag = "" if (ok == bool(representable) and wrong_ok) else "   <-- MISMATCH"
                        problems += bool(flag)
                        print(f"  {task['id']:<22} {rep:<19} representable={str(representable):<5} oracle={'correct' if ok else (res.reason if res else 'inexpressible'):<22} wrong-answer-rejected={wrong_ok}  ({why}){flag}")
                await ps.page.context.close()
    print("problems:", problems)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:] or ["books_listing", "form", "embed"])))
