# Web page representations: token cost vs. LLM read/act accuracy

A reproducible benchmark of how many tokens six representations of a web page
cost an LLM (`claude-sonnet-5`), and how accurately the model can read facts
from the page (READ) and pick the element to act on (ACT) from each one.

Representations: `raw_html` (`page.content()`), `markdown` (markdownify),
`accessibility_tree` (Playwright `aria_snapshot()`), `indexed_dom` (Browser
Use's own DOM serializer), `stagehand_snapshot` (Stagehand v4's own
`page.snapshot()`), `screenshot` (one 1280x800 viewport PNG).

Pages are served locally from committed snapshots and fixtures; nothing
touches a live site during a run. Tasks, prompt template and scoring rules
were pre-registered in `tasks.json` before any model call. See
[METHODOLOGY.md](METHODOLOGY.md).

## Setup

```bash
uv sync                                     # core harness (Python 3.12)
uv sync --project adapters/browser_use      # Browser Use adapter, own lockfile
uv sync --project adapters/stagehand        # Stagehand adapter, own lockfile
uv run playwright install chromium
echo "ANTHROPIC_API_KEY=..." > .env         # gitignored; or export it
```

## Reproduce

```bash
# Phase 1 (pilot): 3 pages x 8 tasks x 6 representations x 3 repeats = 432 calls
uv run python -m wpbench.run --phase pilot --estimate   # free: token counts + cost estimate
uv run python -m wpbench.run --phase pilot
uv run python -m wpbench.summarize <run_id>             # results/summary_pilot.csv, results/charts/pilot/

# Phase 2 (full): 10 pages x 8 tasks x 6 representations x 3 repeats = 1440 calls
uv run python -m wpbench.run --phase full --estimate
uv run python -m wpbench.run --phase full
uv run python -m wpbench.summarize <run_id>             # results/summary.csv, results/charts/
```

`<run_id>` is printed at the end of a run (e.g. `pilot-20261001T170000Z`).
Pass `--seed N` to reproduce a recorded run order.

## Checks that make no API calls

```bash
uv run python scripts/verify_pages.py          # every page renders offline; lists blocked requests
uv run python scripts/validate_tasks.py        # every ACT target resolves uniquely; location tags match geometry
uv run python scripts/selftest_resolution.py   # oracle answers resolve correctly iff representable
uv run python scripts/coverage_report.py       # READ answers / ACT targets present in each representation
```

## Outputs

- `results/raw/<run_id>.jsonl`: one line per call (tokens, usage, answer, resolved element, correctness, latency)
- `results/representations/<run_id>/`: the exact output of every representation for every page load
- `results/runs/<run_id>.json`: versions, seed, call order, machine
- `results/summary.csv`, `results/charts/`, `results/examples/`
- `results/report_full.md`: written report of the full run; `results/report_tables_<phase>.md`:
  Wilson intervals, location breakdown, failure reasons (`uv run python scripts/report_tables.py <run_id>`)
- Post-hoc views excluding pages can be generated with
  `cd scripts && uv run python report_excluding_pages.py <run_id> <page_id> ...` (not part of the pre-registered results)
- `results/aborted/`: invalid runs stopped by harness bugs, kept for transparency, excluded from analysis
