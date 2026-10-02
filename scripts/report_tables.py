"""Reporting tables for a run (no API calls, no rescoring): writes results/report_tables_<phase>.md.

    uv run python scripts/report_tables.py <run_id>

- accuracy per representation with Wilson 95% intervals (calls as trials;
  repeats are nearly deterministic, so intervals over calls are optimistic,
  and task-level counts are shown alongside)
- accuracy by pre-registered location tag
- failure reasons per representation
- a clearly labelled sensitivity line for docs.act.3 (see METHODOLOGY.md);
  it never replaces the pre-registered score
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict

from wpbench import RESULTS_DIR
from wpbench.capture import REPRESENTATIONS


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def is_option_31(r: dict) -> bool:
    """Did a docs.act.3 answer resolve to the '3.1' <option> of the version select?"""
    res = r.get("resolved") or {}
    if res.get("tag") == "option" and res.get("text") == "3.1":  # raw_html, markdown, accessibility_tree
        return True
    # stagehand_snapshot: Stagehand's xpath for the 3rd option of the page's only <select>
    return str(res.get("xpath", "")).endswith("/select[1]/option[3]")


def pct(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({k / n:.0%}, 95% CI {lo:.0%}–{hi:.0%})" if n else "–"


def main(run_id: str) -> None:
    rows = [json.loads(line) for line in (RESULTS_DIR / "raw" / f"{run_id}.jsonl").open()]
    phase = rows[0]["phase"]
    out = [f"# Report tables: {run_id}", "", f"{len(rows)} calls.", ""]

    out += ["## Accuracy per representation", "",
            "| representation | READ (calls) | ACT (calls) | READ tasks correct in all repeats | ACT tasks correct in all repeats |",
            "|---|---|---|---|---|"]
    for rep in REPRESENTATIONS:
        g = [r for r in rows if r["representation"] == rep]
        line = [rep]
        for typ in ("read", "act"):
            t = [r for r in g if r["type"] == typ]
            line.append(pct(sum(r["correct"] for r in t), len(t)))
        for typ in ("read", "act"):
            per_task = defaultdict(list)
            for r in g:
                if r["type"] == typ:
                    per_task[r["task"]].append(r["correct"])
            line.append(f"{sum(all(v) for v in per_task.values())}/{len(per_task)}")
        out.append("| " + " | ".join(line) + " |")

    out += ["", "## Accuracy by location tag (calls correct / calls)", ""]
    locs = sorted({r["location"] for r in rows})
    out += ["| representation | " + " | ".join(locs) + " |", "|---" * (len(locs) + 1) + "|"]
    for rep in REPRESENTATIONS:
        cells = []
        for loc in locs:
            t = [r for r in rows if r["representation"] == rep and r["location"] == loc]
            cells.append(f"{sum(r['correct'] for r in t)}/{len(t)}")
        out.append(f"| {rep} | " + " | ".join(cells) + " |")

    out += ["", "## Failure reasons", ""]
    for rep in REPRESENTATIONS:
        c = Counter(r["reason"] for r in rows if r["representation"] == rep and not r["correct"])
        out.append(f"- **{rep}**: " + (", ".join(f"{k} {v}" for k, v in c.most_common()) or "none"))

    out += ["", "## Sensitivity (NOT the pre-registered score): docs.act.3", "",
            "Pre-registered target: the `<select id=version>`. Counting an answer that resolved to its "
            "`<option>3.1</option>` as correct instead would change ACT totals as follows:", ""]
    for rep in REPRESENTATIONS:
        t = [r for r in rows if r["representation"] == rep and r["type"] == "act"]
        base = sum(r["correct"] for r in t)
        extra = sum(1 for r in t if r["task"] == "docs.act.3" and not r["correct"] and is_option_31(r))
        out.append(f"- {rep}: {base}/{len(t)} → {base + extra}/{len(t)}")

    path = RESULTS_DIR / f"report_tables_{phase}.md"
    path.write_text("\n".join(out) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1])
