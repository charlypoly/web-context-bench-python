"""Run a phase of the benchmark, or estimate its cost.

    uv run python -m wpbench.run --phase pilot --estimate   # count tokens only (free endpoint), print cost
    uv run python -m wpbench.run --phase pilot              # pilot: 3 pages x 6 representations x 3 repeats
    uv run python -m wpbench.run --phase full               # all 10 pages x 6 representations x 3 repeats

Order: for each repeat, pages are visited in a random order; within a page
session, the (task, representation) calls are shuffled. The seed is recorded.
Every call is made exactly once and written to results/raw/<run_id>.jsonl as
soon as it is scored.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from playwright.async_api import async_playwright

from wpbench import RESULTS_DIR, ROOT
from wpbench.capture import REPRESENTATIONS, PageSession
from wpbench.harness import Harness
from wpbench.llm import MAX_TOKENS, MODEL, THINKING, call_model, client, count_tokens, parse_reply, tiktoken_count
from wpbench.pages import pilot_page_ids
from wpbench.prompt import fixed_prompt_text
from wpbench.resolve import resolve_act
from wpbench.scoring import act_target_representable, read_answer_present, score_read
from wpbench.vision import image_accounting

PRICE_PER_MTOK = {"input": 2.00, "output": 10.00}  # claude-sonnet-5, platform.claude.com/docs/en/models/sonnet-5/overview
CONCURRENCY = 4
REPEATS = 3


def load_tasks() -> list[dict]:
    return json.loads((ROOT / "tasks.json").read_text())["tasks"]


def phase_pages(phase: str) -> list[str]:
    if phase == "pilot":
        return pilot_page_ids()
    return [t["page"] for t in load_tasks() if t["id"].endswith(".read.1")]


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def save_session(ps: PageSession, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "raw_html.html").write_text(ps.reps["raw_html"])
    (out / "markdown.md").write_text(ps.reps["markdown"])
    (out / "accessibility_tree.yaml").write_text(ps.reps["accessibility_tree"])
    (out / "indexed_dom.txt").write_text(ps.reps["indexed_dom"])
    (out / "indexed_dom.selector_map.json").write_text(json.dumps(ps.indexed_dom_map, indent=1))
    (out / "stagehand_snapshot.txt").write_text(ps.reps["stagehand_snapshot"])
    (out / "stagehand_snapshot.xpath_map.json").write_text(json.dumps(ps.stagehand_xpath_map, indent=1))
    (out / "screenshot.png").write_bytes(ps.reps["screenshot"])
    truths = {
        tid: {
            "backend_node_id": t.main.backend_node_id if t.main else None,
            "target_id": t.main.target_id if t.main else None,
            "frame_depth": t.main.frame_depth if t.main else None,
            "in_closed_shadow": t.main.in_closed_shadow if t.main else None,
            "box": t.box, "stagehand_key": t.stagehand_key, "stagehand_xpath": t.stagehand_xpath, "error": t.error,
        }
        for tid, t in ps.truths.items()
    }
    (out / "session.json").write_text(json.dumps({
        "page_id": ps.page_id, "url": ps.url, "integrity": ps.integrity,
        "indexed_dom_meta": ps.indexed_dom_meta, "stagehand_meta": ps.stagehand_meta, "ground_truth": truths,
    }, indent=1))


def screenshot_dims(png: bytes) -> tuple[int, int]:
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


async def token_record(api, rep: str, task: dict, page) -> dict:
    full, empty = await asyncio.gather(count_tokens(api, rep, task, page), count_tokens(api, rep, task, None))
    rec = {"count_tokens_full": full, "fixed_prompt_tokens": empty, "representation_tokens": full - empty,
           "fixed_prompt_tokens_tiktoken": tiktoken_count(fixed_prompt_text(rep, task))}
    if rep == "screenshot":
        rec["image"] = image_accounting(*screenshot_dims(page))
        rec["representation_tokens_tiktoken"] = None
    else:
        rec["representation_tokens_tiktoken"] = tiktoken_count(page)
    return rec


async def run_call(api, sem, sh_lock, h, ps, task, rep, base: dict) -> dict:
    page_content = ps.reps[rep]
    async with sem:
        tokens, call = await asyncio.gather(token_record(api, rep, task, page_content), call_model(api, rep, task, page_content))
    rec = {**base, "task": task["id"], "type": task["type"], "location": task["location"], "representation": rep,
           "tokens": tokens, "usage": call.usage, "request_id": call.request_id, "stop_reason": call.stop_reason,
           "latency_s": round(call.latency_s, 3), "api_error": call.error, "reply_text": call.reply_text,
           "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if rep == "screenshot" and call.usage:
        rec["tokens"]["representation_tokens_api"] = call.usage["input_tokens"] - tokens["fixed_prompt_tokens"]

    answer, parse_err = parse_reply(call.reply_text)
    rec["answer"] = answer
    if task["type"] == "read":
        present = read_answer_present(rep, ps, task)
        rec["representable"], rec["representable_note"] = present, "answer string present" if present else (
            "not checkable for images" if present is None else "answer string absent")
        value = answer.get("answer") if answer else None
        correct = score_read(value, task)
        reason = "correct" if correct else (call.error and "api_error") or parse_err or (
            "no_answer" if value is None else "wrong_answer")
        rec["resolved"] = None
    else:
        representable, note = await act_target_representable(rep, ps, task["id"])
        rec["representable"], rec["representable_note"] = representable, note
        if call.error:
            correct, reason, resolved = False, "api_error", None
        elif parse_err:
            correct, reason, resolved = False, parse_err, None
        else:
            if rep == "stagehand_snapshot":
                async with sh_lock:
                    res = await resolve_act(rep, ps, task["id"], answer, h.sh)
            else:
                res = await resolve_act(rep, ps, task["id"], answer, h.sh)
            correct, reason, resolved = res.correct, res.reason, res.resolved
        rec["resolved"] = resolved
    if not correct and rec["representable"] is False and reason not in ("api_error",):
        rec["failure_detail"] = reason
        reason = "not representable"
    rec["correct"], rec["reason"] = correct, reason
    return rec


async def run_phase(phase: str, repeats: int, seed: int, estimate: bool) -> None:
    tasks = load_tasks()
    page_ids = phase_pages(phase)
    rng = random.Random(seed)
    run_id = f"{phase}-{'estimate-' if estimate else ''}{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    api = client()
    meta = {
        "run_id": run_id, "phase": phase, "estimate_only": estimate, "seed": seed, "repeats": repeats,
        "pages": page_ids, "model": MODEL, "max_tokens": MAX_TOKENS, "thinking": THINKING, "concurrency": CONCURRENCY,
        "git_commit": git_commit(), "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "machine": {"platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version()},
        "versions": {pkg: version(pkg) for pkg in ("playwright", "markdownify", "tiktoken", "anthropic")},
        "order": [],
    }
    raw_path = RESULTS_DIR / "raw" / f"{run_id}.jsonl"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    sem, sh_lock = asyncio.Semaphore(CONCURRENCY), asyncio.Lock()
    est = {"input_tokens": 0, "calls": 0, "by_rep": {r: 0 for r in REPRESENTATIONS}}

    async with async_playwright() as p:
        async with Harness(p) as h:
            meta["versions"].update(h.versions)
            for repeat in range(1, (1 if estimate else repeats) + 1):
                order = page_ids[:]
                rng.shuffle(order)
                for page_id in order:
                    page_tasks = [t for t in tasks if t["page"] == page_id]
                    ps = await h.capture(page_id, [t for t in page_tasks if t["type"] == "act"])
                    save_session(ps, RESULTS_DIR / "representations" / run_id / f"repeat{repeat}" / page_id)
                    calls = [(t, r) for t in page_tasks for r in REPRESENTATIONS]
                    rng.shuffle(calls)
                    meta["order"].append({"repeat": repeat, "page": page_id, "calls": [f"{t['id']}|{r}" for t, r in calls]})
                    if estimate:
                        counts = await asyncio.gather(*[count_tokens(api, r, t, ps.reps[r]) for t, r in calls])
                        for (t, r), n in zip(calls, counts):
                            est["input_tokens"] += n
                            est["by_rep"][r] += n
                            est["calls"] += 1
                    else:
                        base = {"run_id": run_id, "phase": phase, "repeat": repeat, "page": page_id, "model": MODEL}
                        recs = await asyncio.gather(*[run_call(api, sem, sh_lock, h, ps, t, r, base) for t, r in calls])
                        with raw_path.open("a") as f:
                            for rec in recs:
                                f.write(json.dumps(rec) + "\n")
                        n_ok = sum(r["correct"] for r in recs)
                        print(f"repeat {repeat} {page_id}: {n_ok}/{len(recs)} correct, "
                              f"{sum(1 for r in recs if r['api_error'])} API errors", flush=True)
                    await ps.page.context.close()

    meta["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    runs_dir = RESULTS_DIR / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    if estimate:
        per_repeat_in = est["input_tokens"]
        total_in = per_repeat_in * repeats
        calls = est["calls"] * repeats
        # Output: replies are short JSON objects; bound by max_tokens.
        out_expected, out_max = calls * 60, calls * MAX_TOKENS
        cost = lambda i, o: i / 1e6 * PRICE_PER_MTOK["input"] + o / 1e6 * PRICE_PER_MTOK["output"]
        meta["estimate"] = {
            "calls": calls, "input_tokens": total_in, "input_tokens_by_rep_per_repeat": est["by_rep"],
            "output_tokens_expected": out_expected, "output_tokens_upper_bound": out_max,
            "cost_usd_expected": round(cost(total_in, out_expected), 2),
            "cost_usd_upper_bound": round(cost(total_in, out_max), 2),
        }
        print(json.dumps(meta["estimate"], indent=2))
    (runs_dir / f"{run_id}.json").write_text(json.dumps(meta, indent=1))
    print(f"run {run_id} done; metadata in results/runs/{run_id}.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["pilot", "full"], required=True)
    ap.add_argument("--repeats", type=int, default=REPEATS)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--estimate", action="store_true", help="count tokens and estimate cost; no model calls")
    args = ap.parse_args()
    seed = args.seed if args.seed is not None else int(time.time())
    asyncio.run(run_phase(args.phase, args.repeats, seed, args.estimate))


if __name__ == "__main__":
    sys.exit(main())
