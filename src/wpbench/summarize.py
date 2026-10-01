"""Aggregate results/raw/<run_id>.jsonl into results/summary.csv and results/charts/.

    uv run python -m wpbench.summarize <run_id> [<run_id> ...]

summary.csv has one row per (representation, page) plus one "ALL" row per
representation. Token columns are medians over calls; for the screenshot the
Anthropic column is the API-reported representation tokens
(usage.input_tokens - fixed prompt), and tiktoken does not apply.
tokens_per_correct = total API input tokens over all calls / number correct.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from wpbench import RESULTS_DIR  # noqa: E402
from wpbench.capture import REPRESENTATIONS  # noqa: E402

# Chart styling (dataviz reference palette, light mode).
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE = "#2a78d6", "#eb6834"


def load(run_ids: list[str]) -> list[dict]:
    rows = []
    for rid in run_ids:
        with (RESULTS_DIR / "raw" / f"{rid}.jsonl").open() as f:
            rows += [json.loads(line) for line in f]
    return rows


def rep_tokens(r: dict) -> float | None:
    t = r["tokens"]
    return t.get("representation_tokens_api") if r["representation"] == "screenshot" else t["representation_tokens"]


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _acc(rows):
    return (sum(r["correct"] for r in rows) / len(rows)) if rows else None


def summarize(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for r in rows:
        groups[(r["representation"], r["page"])].append(r)
        groups[(r["representation"], "ALL")].append(r)
    out = []
    pages = sorted({r["page"] for r in rows}) + ["ALL"]
    for rep in REPRESENTATIONS:
        for page in pages:
            g = groups.get((rep, page), [])
            if not g:
                continue
            reads = [r for r in g if r["type"] == "read"]
            acts = [r for r in g if r["type"] == "act"]
            correct = sum(r["correct"] for r in g)
            total_input = sum(r["usage"]["input_tokens"] for r in g if r["usage"])
            out.append({
                "representation": rep, "page": page, "calls": len(g),
                "median_representation_tokens_anthropic": _median(rep_tokens(r) for r in g),
                "median_representation_tokens_count_endpoint": _median(r["tokens"]["representation_tokens"] for r in g),
                "median_representation_tokens_tiktoken_o200k": _median(r["tokens"]["representation_tokens_tiktoken"] for r in g),
                "median_fixed_prompt_tokens_anthropic": _median(r["tokens"]["fixed_prompt_tokens"] for r in g),
                "median_fixed_prompt_tokens_tiktoken_o200k": _median(r["tokens"]["fixed_prompt_tokens_tiktoken"] for r in g),
                "median_api_input_tokens": _median(r["usage"]["input_tokens"] if r["usage"] else None for r in g),
                "read_accuracy": _acc(reads), "read_n": len(reads),
                "act_accuracy": _acc(acts), "act_n": len(acts),
                "act_not_representable": sum(r["reason"] == "not representable" for r in acts),
                "read_not_representable": sum(r["reason"] == "not representable" for r in reads),
                "api_errors": sum(bool(r["api_error"]) for r in g),
                "correct": correct,
                "tokens_per_correct": round(total_input / correct, 1) if correct else None,
            })
    return out


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=10)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def charts(summary: list[dict], out_dir, title_suffix: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    allrows = {s["representation"]: s for s in summary if s["page"] == "ALL"}
    reps = [r for r in REPRESENTATIONS if r in allrows]
    page_rows = [s for s in summary if s["page"] != "ALL"]

    # 1. Tokens by representation, log scale: bar = median over all calls, dots = per-page medians.
    fig, ax = plt.subplots(figsize=(9, 4.2), facecolor=SURFACE)
    _style(ax)
    y = range(len(reps))
    med = [allrows[r]["median_representation_tokens_anthropic"] for r in reps]
    ax.barh(list(y), med, color=BLUE, height=0.5)
    for i, r in enumerate(reps):
        pts = [s["median_representation_tokens_anthropic"] for s in page_rows if s["representation"] == r]
        ax.scatter(pts, [i] * len(pts), s=36, color=INK, zorder=3, edgecolor=SURFACE, linewidth=1.5)
        ax.text(med[i] * 1.08, i + 0.32, f"{med[i]:,.0f}", color=INK, fontsize=9, va="center")
    ax.set_xscale("log")
    ax.set_yticks(list(y), reps)
    ax.invert_yaxis()
    ax.set_xlabel("Representation tokens (Anthropic count; log scale)", color=INK2)
    ax.set_title(f"Tokens by representation{title_suffix}\nbar = median of all calls, dots = per-page medians",
                 loc="left", color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(out_dir / "tokens_by_representation.png", dpi=160)
    plt.close(fig)

    # 2. Accuracy by representation: READ and ACT (two series, legend + direct labels).
    fig, ax = plt.subplots(figsize=(9, 4.6), facecolor=SURFACE)
    _style(ax)
    h = 0.36
    for k, (key, color, label) in enumerate([("read_accuracy", BLUE, "READ"), ("act_accuracy", ORANGE, "ACT")]):
        vals = [allrows[r][key] or 0 for r in reps]
        ys = [i + (k - 0.5) * (h + 0.04) for i in range(len(reps))]
        ax.barh(ys, vals, height=h, color=color, label=label)
        for yy, v in zip(ys, vals):
            ax.text(v + 0.01, yy, f"{v:.0%}", va="center", fontsize=9, color=INK)
    ax.set_xlim(0, 1.08)
    ax.set_yticks(range(len(reps)), reps)
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.legend(frameon=False, loc="lower right", labelcolor=INK)
    ax.set_title(f"Accuracy by representation{title_suffix}", loc="left", color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(out_dir / "accuracy_by_representation.png", dpi=160)
    plt.close(fig)

    # 3. Tokens vs ACT accuracy: one point per representation, direct-labeled.
    fig, ax = plt.subplots(figsize=(8, 5), facecolor=SURFACE)
    _style(ax)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    for r in reps:
        x, yv = allrows[r]["median_representation_tokens_anthropic"], allrows[r]["act_accuracy"] or 0
        ax.scatter([x], [yv], s=70, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=3)
        ax.annotate(r, (x, yv), textcoords="offset points", xytext=(8, 6), fontsize=10, color=INK)
    ax.set_xscale("log")
    ax.set_ylim(-0.03, 1.05)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xlabel("Median representation tokens (log scale)", color=INK2)
    ax.set_ylabel("ACT accuracy", color=INK2)
    ax.set_title(f"Tokens vs ACT accuracy{title_suffix}", loc="left", color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(out_dir / "tokens_vs_act_accuracy.png", dpi=160)
    plt.close(fig)


def main(run_ids: list[str]) -> None:
    rows = load(run_ids)
    summary = summarize(rows)
    phase = rows[0]["phase"] if rows else "unknown"
    path = RESULTS_DIR / "summary.csv" if phase == "full" else RESULTS_DIR / f"summary_{phase}.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)
    charts(summary, RESULTS_DIR / "charts" / ("" if phase == "full" else phase), f" ({phase}, {len(rows)} calls)")
    print(f"wrote {path} and charts for {len(rows)} calls")


if __name__ == "__main__":
    main(sys.argv[1:])
