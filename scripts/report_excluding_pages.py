"""Post-hoc view of a run with some pages excluded, recomputed from the raw log only.

    uv run python scripts/report_excluding_pages.py <run_id> <page_id> [<page_id> ...]

No model calls and no rescoring: every row keeps the `correct`, `reason` and
token fields recorded during the run; rows for the excluded pages are dropped.
This view was requested after the results were seen. It does not replace the
pre-registered all-pages results (results/report_full.md,
results/report_tables_<phase>.md).

Writes results/report_<phase>_excluding_<pages>.md with:
- the overall results table
- the breakdown by pre-registered location tag
- the Browser Use (indexed_dom) vs Stagehand (stagehand_snapshot) comparison
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict

from report_tables import pct

from wpbench import RESULTS_DIR
from wpbench.capture import REPRESENTATIONS

BU, SH = "indexed_dom", "stagehand_snapshot"


def rep_tokens(r: dict) -> int | None:
    t = r["tokens"]
    return t.get("representation_tokens_api") if r["representation"] == "screenshot" else t["representation_tokens"]


def task_level(rows: list[dict], rep: str, typ: str) -> tuple[int, int]:
    per_task = defaultdict(list)
    for r in rows:
        if r["representation"] == rep and r["type"] == typ:
            per_task[r["task"]].append(r["correct"])
    return sum(all(v) for v in per_task.values()), len(per_task)


def main(run_id: str, excluded: list[str]) -> None:
    all_rows = [json.loads(line) for line in (RESULTS_DIR / "raw" / f"{run_id}.jsonl").open()]
    unknown = set(excluded) - {r["page"] for r in all_rows}
    if unknown:
        sys.exit(f"unknown page(s): {sorted(unknown)}")
    rows = [r for r in all_rows if r["page"] not in excluded]
    pages = sorted({r["page"] for r in rows})
    phase = rows[0]["phase"]
    n_read = len({r["task"] for r in rows if r["type"] == "read"})
    n_act = len({r["task"] for r in rows if r["type"] == "act"})

    out = [
        f"# {run_id}, excluding {', '.join(excluded)}",
        "",
        "> **Post-hoc view, requested after the results were seen.** It does not replace the pre-registered",
        "> all-pages results in [report_full.md](report_full.md). Recomputed from",
        f"> `results/raw/{run_id}.jsonl` only: no model calls, no rescoring; rows for the excluded page(s) are dropped.",
        "",
        f"{len(rows)} of {len(all_rows)} calls, {len(pages)} pages, {n_read} READ and {n_act} ACT tasks.",
        "Intervals are Wilson 95% over calls. Repeats are nearly deterministic, so they are optimistic; task-level",
        "counts (correct in all 3 repeats) are shown alongside.",
        "",
        "## Overall",
        "",
        "| representation | READ (calls) | ACT (calls) | READ tasks | ACT tasks | median representation tokens per page (range) | input tokens per correct answer |",
        "|---|---|---|---|---|---|---|",
    ]
    for rep in REPRESENTATIONS:
        g = [r for r in rows if r["representation"] == rep]
        reads = [r for r in g if r["type"] == "read"]
        acts = [r for r in g if r["type"] == "act"]
        per_page = [statistics.median(rep_tokens(r) for r in g if r["page"] == p) for p in pages]
        correct = sum(r["correct"] for r in g)
        total_in = sum(r["usage"]["input_tokens"] for r in g)
        rt, rn = task_level(rows, rep, "read")
        at, an = task_level(rows, rep, "act")
        out.append(
            f"| {rep} | {pct(sum(r['correct'] for r in reads), len(reads))} | {pct(sum(r['correct'] for r in acts), len(acts))} "
            f"| {rt}/{rn} | {at}/{an} | {statistics.median(per_page):,.0f} ({min(per_page):,.0f}–{max(per_page):,.0f}) "
            f"| {total_in / correct:,.0f} |")

    locs = sorted({r["location"] for r in rows})
    out += ["", "## Accuracy by location tag (calls correct / calls)", "",
            "| representation | " + " | ".join(locs) + " |", "|---" * (len(locs) + 1) + "|"]
    for rep in REPRESENTATIONS:
        cells = []
        for loc in locs:
            t = [r for r in rows if r["representation"] == rep and r["location"] == loc]
            cells.append(f"{sum(r['correct'] for r in t)}/{len(t)}")
        out.append(f"| {rep} | " + " | ".join(cells) + " |")

    # --- Browser Use vs Stagehand ---------------------------------------------
    def stats(rep):
        g = [r for r in rows if r["representation"] == rep]
        return {
            "read": sum(r["correct"] for r in g if r["type"] == "read"),
            "read_n": sum(1 for r in g if r["type"] == "read"),
            "act": sum(r["correct"] for r in g if r["type"] == "act"),
            "act_n": sum(1 for r in g if r["type"] == "act"),
            "rep_tokens": sum(rep_tokens(r) for r in g),
            "input": sum(r["usage"]["input_tokens"] for r in g),
            "correct": sum(r["correct"] for r in g),
        }

    bu, sh = stats(BU), stats(SH)
    out += ["", "## Browser Use (indexed_dom) vs Stagehand (stagehand_snapshot)", "",
            "| | Browser Use | Stagehand | Stagehand ÷ Browser Use |", "|---|---|---|---|",
            f"| READ calls correct | {bu['read']}/{bu['read_n']} | {sh['read']}/{sh['read_n']} | |",
            f"| ACT calls correct | {bu['act']}/{bu['act_n']} | {sh['act']}/{sh['act_n']} | |",
            f"| READ tasks (all repeats) | {'/'.join(map(str, task_level(rows, BU, 'read')))} | {'/'.join(map(str, task_level(rows, SH, 'read')))} | |",
            f"| ACT tasks (all repeats) | {'/'.join(map(str, task_level(rows, BU, 'act')))} | {'/'.join(map(str, task_level(rows, SH, 'act')))} | |",
            f"| representation tokens, all calls | {bu['rep_tokens']:,} | {sh['rep_tokens']:,} | {sh['rep_tokens'] / bu['rep_tokens']:.2f}× |",
            f"| API input tokens, all calls | {bu['input']:,} | {sh['input']:,} | {sh['input'] / bu['input']:.2f}× |",
            f"| input tokens per correct answer | {bu['input'] / bu['correct']:,.0f} | {sh['input'] / sh['correct']:,.0f} | {(sh['input'] / sh['correct']) / (bu['input'] / bu['correct']):.2f}× |",
            "", "### Per page", "",
            "| page | Browser Use tokens | Stagehand tokens | ratio | Browser Use READ / ACT | Stagehand READ / ACT |",
            "|---|---|---|---|---|---|"]
    ratios = []
    for p in pages:
        cells = []
        for rep in (BU, SH):
            g = [r for r in rows if r["representation"] == rep and r["page"] == p]
            cells.append((statistics.median(rep_tokens(r) for r in g),
                          f"{sum(r['correct'] for r in g if r['type'] == 'read')}/{sum(1 for r in g if r['type'] == 'read')}",
                          f"{sum(r['correct'] for r in g if r['type'] == 'act')}/{sum(1 for r in g if r['type'] == 'act')}"))
        ratio = cells[1][0] / cells[0][0]
        ratios.append(ratio)
        out.append(f"| {p} | {cells[0][0]:,.0f} | {cells[1][0]:,.0f} | {ratio:.2f}× | {cells[0][1]} / {cells[0][2]} | {cells[1][1]} / {cells[1][2]} |")
    out += ["", f"Median per-page token ratio (Stagehand ÷ Browser Use): {statistics.median(ratios):.2f}× "
                f"(range {min(ratios):.2f}×–{max(ratios):.2f}×).", ""]

    # Tasks where exactly one of the two was wrong in at least one repeat.
    out += ["### Tasks where the two differ", "", "| task | location | Browser Use | Stagehand | failure reason |", "|---|---|---|---|---|"]
    by = defaultdict(dict)
    for r in rows:
        if r["representation"] in (BU, SH):
            by[r["task"]].setdefault(r["representation"], []).append(r)
    for task in sorted(by):
        b, s = by[task][BU], by[task][SH]
        bc, sc = sum(r["correct"] for r in b), sum(r["correct"] for r in s)
        if bc != sc:
            reasons = "; ".join(sorted({f"{r['representation']}: {r.get('failure_detail') or r['reason']}"
                                        for r in b + s if not r["correct"]}))
            out.append(f"| {task} | {b[0]['location']} | {bc}/{len(b)} | {sc}/{len(s)} | {reasons} |")
    both = [t for t in sorted(by) if not any(r["correct"] for r in by[t][BU] + by[t][SH])]
    out += ["", "Missed by both in every repeat: " + (", ".join(both) or "none") + "."]

    name = "_".join(excluded)
    path = RESULTS_DIR / f"report_{phase}_excluding_{name}.md"
    path.write_text("\n".join(out) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
