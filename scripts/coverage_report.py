"""Coverage check (no API calls): which READ answers and ACT targets each representation contains.

For every page: READ answers present verbatim (after normalization) in each
text representation, ACT targets representable, and representation size.
Used to confirm that Browser Use's and Stagehand's outputs cover the same
share of each page.

    uv run python scripts/coverage_report.py
"""

from __future__ import annotations

import asyncio
import json

from playwright.async_api import async_playwright

from wpbench import ROOT
from wpbench.capture import REPRESENTATIONS
from wpbench.harness import Harness
from wpbench.scoring import act_target_representable, read_answer_present

TEXT_REPS = [r for r in REPRESENTATIONS if r != "screenshot"]


async def main() -> None:
    tasks = json.loads((ROOT / "tasks.json").read_text())["tasks"]
    totals = {r: [0, 0, 0, 0] for r in REPRESENTATIONS}  # read present, read n, act representable, act n
    async with async_playwright() as p:
        async with Harness(p) as h:
            print(f"{'page':<16}" + "".join(f"{r:>22}" for r in TEXT_REPS))
            for page_id in h.pages:
                page_tasks = [t for t in tasks if t["page"] == page_id]
                ps = await h.capture(page_id, [t for t in page_tasks if t["type"] == "act"])
                cells = []
                for r in REPRESENTATIONS:
                    reads = [read_answer_present(r, ps, t) for t in page_tasks if t["type"] == "read"]
                    acts = [(await act_target_representable(r, ps, t["id"]))[0] for t in page_tasks if t["type"] == "act"]
                    totals[r][0] += sum(bool(x) for x in reads)
                    totals[r][1] += len(reads)
                    totals[r][2] += sum(bool(x) for x in acts)
                    totals[r][3] += len(acts)
                    if r in TEXT_REPS:
                        cells.append(f"R{sum(bool(x) for x in reads)}/{len(reads)} A{sum(bool(x) for x in acts)}/{len(acts)} {len(ps.reps[r])/1000:>6.1f}k")
                print(f"{page_id:<16}" + "".join(f"{c:>22}" for c in cells))
                await ps.page.context.close()
    print("\nTOTAL (READ answers present / ACT targets representable):")
    for r, (rp, rn, ap, an) in totals.items():
        read = f"{rp}/{rn}" if r != "screenshot" else "n/a"
        print(f"  {r:<20} READ {read:<7} ACT {ap}/{an}")


if __name__ == "__main__":
    asyncio.run(main())
