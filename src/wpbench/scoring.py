"""Deterministic scoring helpers: READ normalization and representability checks.

Representability is decided from the captured representation and the live
page, never from the model's answer. A failed answer on a task whose target
(ACT) or answer (READ) is absent from the representation is recorded with
reason "not representable".
"""

from __future__ import annotations

import re
import unicodedata

from wpbench.capture import PageSession

_DASHES = re.compile(r"[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]")
# A backslash before ASCII punctuation is an escape, not content (e.g. markdownify's "locked\_out\_user").
_ESCAPES = re.compile(r"\\([!-/:-@\[-`{-~])")


# Keys in Playwright's aria snapshot YAML that are not ARIA roles.
NON_ROLE_KEYS = {"text", "/url", "/placeholder", "/children"}
_ARIA_KEY = re.compile(r'^([a-z/]+)(?: "((?:[^"\\]|\\.)*)")?')


def parse_aria_line(line: str) -> tuple[str, str | None] | None:
    """(role, name) of one line of Playwright's aria snapshot, undoing YAML key quoting."""
    rest = line.strip()
    if not rest.startswith("- "):
        return None
    rest = rest[2:]
    if rest.startswith("'"):  # YAML single-quoted key: '' is an escaped quote
        end, i = None, 1
        while i < len(rest):
            if rest[i] == "'":
                if i + 1 < len(rest) and rest[i + 1] == "'":
                    i += 2
                    continue
                end = i
                break
            i += 1
        if end is None:
            return None
        rest = rest[1:end].replace("''", "'")
    m = _ARIA_KEY.match(rest)
    if not m:
        return None
    name = m.group(2)
    return m.group(1), (name.replace('\\"', '"').replace("\\\\", "\\") if name is not None else None)


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = _ESCAPES.sub(r"\1", s)
    s = _DASHES.sub("-", s)
    s = " ".join(s.split())
    if s.endswith("."):
        s = s[:-1]
    return s.casefold()


def score_read(answer: object, task: dict) -> bool:
    if not isinstance(answer, str):
        return False
    got = normalize(answer)
    return any(got == normalize(a) for a in [task["answer"], *task.get("aliases", [])])


def read_answer_present(rep: str, ps: PageSession, task: dict) -> bool | None:
    """Does the expected answer (or an alias) appear verbatim in a text representation? None for screenshots."""
    if rep == "screenshot":
        return None
    text = normalize(ps.reps[rep])
    return any(normalize(a) in text for a in [task["answer"], *task.get("aliases", [])])


async def _target_strings(ps: PageSession, truth) -> list[str]:
    """Texts a Markdown answer could use to name the target: its text, labels, placeholder, aria-label."""
    handle = await ps.page.locator(truth.main.chain[0]).element_handle()
    return await handle.evaluate(
        "e => [e.innerText, e.getAttribute('aria-label'), e.getAttribute('placeholder'), e.getAttribute('title'),"
        " (e.type === 'submit' || e.type === 'button') ? e.value : null,"
        " ...Array.from(e.labels || []).map(l => l.innerText)].filter(s => s && s.trim())")


async def act_target_representable(rep: str, ps: PageSession, task_id: str) -> tuple[bool | None, str]:
    """Is the ground-truth target present in (expressible through) this representation?"""
    truth = ps.truths[task_id]
    if truth.main is None:
        return None, "ground truth error"
    top_level = not truth.main.frame_depth and not truth.main.in_shadow

    if rep == "raw_html":
        # page.content() serializes the top document's light DOM only.
        return top_level, "in top document" if top_level else "inside iframe or shadow root"

    if rep == "markdown":
        if not top_level:
            return False, "inside iframe or shadow root"
        md = normalize(ps.reps["markdown"])
        strings = [normalize(s) for s in await _target_strings(ps, truth)]
        hit = [s for s in strings if s and s in md]
        return bool(hit), f"target text in markdown: {hit[:1]}" if hit else f"none of {strings[:4]} in markdown"

    if rep == "accessibility_tree":
        if not top_level:
            return False, "inside iframe or shadow root"
        own = await ps.page.locator(truth.main.chain[0]).aria_snapshot()
        node = parse_aria_line(own.splitlines()[0]) if own.strip() else None
        if node is None or node[0] in NON_ROLE_KEYS:
            return False, f"target has no role in the snapshot ({own.splitlines()[0][:60] if own.strip() else 'empty'!r})"
        present = node in {parse_aria_line(l) for l in ps.reps["accessibility_tree"].splitlines()}
        return present, f"node {node} {'in' if present else 'not in'} snapshot"

    if rep == "indexed_dom":
        ident = (truth.main.target_id, truth.main.backend_node_id)
        present = any((n["target_id"], n["backend_node_id"]) == ident for n in ps.indexed_dom_map.values())
        return present, "in selector map" if present else "not in selector map"

    if rep == "stagehand_snapshot":
        if truth.stagehand_key is None:
            return False, "no Stagehand id for target"
        present = f"[{truth.stagehand_key}]" in ps.reps["stagehand_snapshot"]
        return present, f"[{truth.stagehand_key}] {'in' if present else 'not in'} formatted tree"

    if rep == "screenshot":
        b = truth.box
        if not b or b["width"] <= 0 or b["height"] <= 0:
            return False, "not rendered"
        visible_w = min(b["x"] + b["width"], 1280) - max(b["x"], 0)
        visible_h = min(b["y"] + b["height"], 800) - max(b["y"], 0)
        present = visible_w > 0 and visible_h > 0
        return present, "intersects viewport" if present else "outside viewport"

    raise ValueError(rep)
