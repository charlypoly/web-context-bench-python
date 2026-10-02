# Full run report: full-20261002T073411Z

| | |
|---|---|
| Run | 10 pages × 8 tasks × 6 representations × 3 repeats = 1,440 calls |
| Model | `claude-sonnet-5`, thinking disabled, default temperature |
| Date | 2026-10-02 |
| Errors | 0 API errors, 0 harness errors |
| Billed | 10,681,308 input and 22,274 output tokens (about $21.59) |
| Variation across repeats | 1 of 480 task × representation pairs |

Method, deviations and incidents: [METHODOLOGY.md](../METHODOLOGY.md). Tables with 95% Wilson intervals, the breakdown by location and failure reasons: [report_tables_full.md](report_tables_full.md). Per page: [summary.csv](summary.csv). Charts: [charts/](charts/).

**Sample size.** The run has 50 READ and 30 ACT tasks. Repeats were almost deterministic, so the effective sample is the tasks, not the calls. Differences of one or two tasks are within noise.

## 1. Overall

| Representation | READ calls | ACT calls | READ tasks (all repeats correct) | ACT tasks | Input tokens per correct answer: all pages / without the table page |
|---|---|---|---|---|---|
| raw_html | 138/150 (92%) | 71/90 (79%) | 46/50 | 23/30 | 10,634 / 5,094 |
| markdown | 120/150 (80%) | 63/90 (70%) | 40/50 | 21/30 | 5,698 / 1,992 |
| accessibility_tree | 132/150 (88%) | 75/90 (83%) | 44/50 | 25/30 | 11,656 / 2,708 |
| indexed_dom (Browser Use) | 129/150 (86%) | **87/90 (97%)** | 43/50 | **29/30** | 9,904 / **1,965** |
| stagehand_snapshot | **144/150 (96%)** | **87/90 (97%)** | **48/50** | **29/30** | 10,847 / 3,196 |
| screenshot | 108/150 (72%) | 66/90 (73%) | 36/50 | 22/30 | **2,061** / 1,992 |

## 2. Representation tokens per page

Median Anthropic count, page content only. The fixed prompt adds 132–166 tokens per call.

| Page | raw_html | markdown | accessibility_tree | indexed_dom | stagehand_snapshot | screenshot |
|---|---|---|---|---|---|---|
| article | 3,571 | 1,691 | 2,551 | 1,977 | 3,118 | 1,337 |
| books_listing | 15,118 | 4,902 | 6,527 | 4,148 | 7,416 | 1,337 |
| books_product | 3,203 | 724 | 1,021 | 758 | 1,260 | 1,337 |
| dashboard | 3,265 | 817 | 1,812 | 1,504 | 2,600 | 1,337 |
| docs | 3,396 | 1,267 | 2,957 | 1,754 | 4,303 | 1,337 |
| embed | 1,784 | 285 | 565 | 911 | 1,591 | 1,337 |
| form | 3,109 | 475 | 1,140 | 1,393 | 2,401 | 1,337 |
| saucedemo_login | 1,091 | 107 | 134 | 192 | 403 | 1,337 |
| serp | 3,603 | 1,470 | 2,442 | 1,786 | 3,307 | 1,337 |
| table | 52,977 | 30,087 | **79,719** | 73,271 | 76,702 | 1,337 |

o200k counts are lower on every text representation: by 17–34% in total (`summary.csv`).

## 3. What each representation can't see

These are structural results, from the location breakdown and the representability check:

- **raw_html, markdown and accessibility_tree** (default `aria_snapshot()`) can't see either iframe or the closed shadow root. They score 0/21 on those calls; raw_html gets nothing from the promo widget's `<script>` source this time either.
- **markdown** also loses form state (selected options, pre-filled values) and inputs that have no visible label. On those calls it scores 6/24 on attribute_only tasks and 0/9 on the saucedemo login inputs.
- **The screenshot** sees only the viewport. It scores 3/39 below the fold and 0/27 far below it, and 129/129 above the fold.
- **indexed_dom and stagehand_snapshot** are the only representations that reach inside both iframes and the closed shadow root. Both score 21/21 on those calls.

## 4. Browser Use vs Stagehand

**Coverage.** Both cover the whole page: Browser Use runs with `viewport_threshold=None`, a documented deviation from its agent default. Both pierce same-origin iframes, cross-site out-of-process iframes and closed shadow roots.

**ACT: tied**, 87/90 calls and 29/30 tasks each.
- **Stagehand's only miss** was `docs.act.3`, all three repeats. It answered the `<option>3.1</option>`; the pre-registered target is the `<select>`. That answer is defensible: if it counted, Stagehand would be at 90/90. Scoring stays as pre-registered.
- **Browser Use's only miss** was `serp.act.2` ("go to page 2"), all three repeats. Browser Use's serializer drops text nodes of one character or less (`dom/serializer/serializer.py:557` and `:1172`), so the pagination links "2"–"9" appear as empty `<a />` elements.

**READ: Stagehand ahead**, 144/150 vs 129/150 calls (48/50 vs 43/50 tasks).
- **Missed by both:** the star rating on both books pages, which exists only as a CSS class.
- **Missed only by Browser Use:**
  - which option is selected in a `<select>` (3 tasks: `form.read.1`, `docs.read.2`, `dashboard.read.5`). It lists the options without marking the selected one;
  - text inside the inline SVG chart (`dashboard.read.1`);
  - the single-character review count "0" (`books_product.read.5`).

**Tokens: Stagehand costs more on every page.**
- **Ratio per page:** 1.58× to 2.45× Browser Use's tokens, median 1.74×.
- **Total over the nine pages other than the table:** 26,399 vs 14,423 tokens, 1.83×.
- **The 500-row table** is nearly even: 76,702 vs 73,271 tokens, 1.05×.

**Tokens per correct answer.** On the nine non-table pages: Browser Use 1,965, Stagehand 3,196, so Stagehand is 63% higher. On all pages: 9,904 vs 10,847, Stagehand 10% higher.

**Summary.** For the same ACT accuracy, Stagehand's snapshot buys 15 more correct READ calls out of 150 (5 more tasks) at roughly 1.7–1.8× Browser Use's tokens on typical pages. Most of Browser Use's READ losses come from two specific serializer choices: no selected-option state and no single-character text. They don't come from page coverage.

## 5. The article's working conclusion

> "the accessibility tree keeps interactive structure at a fraction of HTML's cost, and pruned hybrids do best for agents"

**Not supported as stated.**

**Is the accessibility tree "a fraction of HTML's cost"?** Usually: its median is 0.49× raw HTML, ranging from 0.12× to 0.87×. But not always: on the long table it costs **1.50× raw HTML** (79,719 vs 52,977 tokens).

**Does it "keep interactive structure"?** Only in the top document. Default `aria_snapshot()` drops everything inside iframes and closed shadow roots (0/21 calls). On top-document pages it did well: ACT 75/81 calls outside embed. Its other ACT misses were `docs.act.3` (the same select/option ambiguity) and the `<summary>` element, which has no role.

**Do "pruned hybrids do best for agents"?**
- **ACT accuracy: yes.** The two library serializers lead (97% vs at most 83% for anything else). They're the only representations that pierce iframes and closed shadow roots.
- **Cost-efficiency: no.** Off the table page, the cheapest representations per correct answer were Browser Use (1,965), the screenshot and Markdown (both 1,992). Stagehand's snapshot (3,196) is 1.6× more.
- **Long pages:** the table cost about the same for both libraries' output as for the accessibility tree (73–80k tokens). On that page the screenshot was 50× cheaper but answered only half the tasks.

**What the data supports instead:**
1. For acting on pages with iframes or closed shadow roots, use a serializer that pierces them (Browser Use's or Stagehand's). Neither raw HTML, Markdown nor Playwright's default accessibility snapshot can express those targets at all.
2. Among those two, Browser Use's is about 1.7× cheaper for equal ACT accuracy, and Stagehand's is better for reading facts, at that extra cost.
3. On simple top-document pages, the plain accessibility tree, and raw HTML for READ (92%), are competitive.

## 6. Where Stagehand underperforms another representation

These are stated explicitly, as you asked:

- **Tokens vs Browser Use:** more on every page (1.05×–2.45×), for identical ACT accuracy. Tokens per correct off the table page: 3,196 vs 1,965, about 63% more.
- **Tokens vs the accessibility tree:** more on 9 of 10 pages (median 1.39×; 2.8–3.0× on embed and saucedemo_login). Where both see the target, they're tied on most pages:
  - **Same accuracy:** article (15/15 READ, 9/9 ACT for both), books_listing (12/15 READ, 9/9 ACT), books_product (12/15, 9/9), dashboard (15/15, 9/9), form (15/15, 9/9), saucedemo_login (15/15, 9/9), docs (15/15, 6/9) and table (15/15, 9/9).
  - **Stagehand ahead** only on embed (iframes and closed shadow root) and serp (`<summary>` element).
- **Tokens vs Markdown:** on article, books_listing and serp, Markdown matched or nearly matched Stagehand's accuracy at about 44–66% of its tokens. On article, Markdown also scored 15/15 READ and 9/9 ACT.
- **Tokens per correct vs the screenshot:** 3,196 vs 1,992 off the table page, but the screenshot fails everything below the fold.
- **ACT vs Browser Use on `docs.act.3`:** Stagehand 0/3 under the pre-registered target; Browser Use 3/3.

## 7. Fairness notes

- **Browser Use:**
  - Run with `viewport_threshold=None`, a non-default setting. It was decided before any model output, to give equal page coverage. On books_listing, the default would have dropped 69 of 234 indices.
  - Its agent would have truncated the table page at 40,000 characters. We sent it untruncated.
  - Its serialization adds empty `style=""` attributes to form controls. This happens after all other captures and affects no selector.
- **Stagehand** ran in its own browser: same binary and flags, fresh tab per page session, viewport verified at 1280×800 on every load.
- **Prompts:** neither library got its own prompt, agent loop, scrolling or retries. Both received the same generic prompt and the same model.
- **Incidents:** three harness bugs were found, fixed, and the affected phase rerun from scratch each time (two in the pilot, one in the first full run). Invalid runs are in `results/aborted/` and logged in METHODOLOGY.
- **Scope:** 10 pages, 80 tasks, one model. Seven pages are fixtures written for this benchmark, and three are practice sites.
