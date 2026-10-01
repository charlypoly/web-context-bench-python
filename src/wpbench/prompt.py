"""Build the one prompt template used for every representation (pre-registered in tasks.json)."""

from __future__ import annotations

import base64
import json
from functools import lru_cache

from wpbench import ROOT


@lru_cache
def protocol() -> dict:
    return json.loads((ROOT / "tasks.json").read_text())["protocol"]


def answer_format(rep: str, task: dict) -> str:
    formats = protocol()["prompt"]["answer_formats"]
    return formats["read"] if task["type"] == "read" else formats["act"][rep]


def _fill(template: str, **values: str) -> str:
    # str.replace, not str.format: the template contains literal JSON braces.
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    return template


def task_text(task: dict) -> str:
    return task["question"] if task["type"] == "read" else task["goal"]


def build_user_content(rep: str, task: dict, page: str | bytes | None) -> list[dict]:
    """User message content blocks. page=None builds the empty-page variant used to count the fixed prompt."""
    tmpl = protocol()["prompt"]["user_template"]
    common = {"TASK_TYPE": task["type"].upper(), "TASK": task_text(task), "ANSWER_FORMAT": answer_format(rep, task)}
    if rep != "screenshot":
        return [{"type": "text", "text": _fill(tmpl, PAGE=page if page is not None else "", **common)}]
    before, after = tmpl.split("{PAGE}")
    blocks = [{"type": "text", "text": _fill(before, **common)}]
    if page is not None:
        blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(page).decode()},
            # Reject instead of silently downsizing: the coordinates must map 1:1 onto the screenshot.
            "transformations": {"oversized_image": "error"},
        })
    blocks.append({"type": "text", "text": _fill(after, **common)})
    return blocks


def system_prompt() -> str:
    return protocol()["prompt"]["system"]


def fixed_prompt_text(rep: str, task: dict) -> str:
    """All prompt text except the page content (system + user), for tiktoken counts."""
    blocks = build_user_content(rep, task, None)
    return system_prompt() + "\n" + "".join(b["text"] for b in blocks if b["type"] == "text")
