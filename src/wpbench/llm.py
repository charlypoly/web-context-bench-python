"""Anthropic API access: token counting and the model call. No retries, ever.

The API key is read from ANTHROPIC_API_KEY (or a gitignored .env file); it is
never printed, logged or written to results.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass

import anthropic
import tiktoken
from dotenv import load_dotenv

from wpbench import ROOT
from wpbench.prompt import build_user_content, protocol, system_prompt

MODEL = "claude-sonnet-5"
MAX_TOKENS = 512
TIMEOUT_S = 120.0
# Sonnet 5 rejects non-default temperature/top_p/top_k, so none are sent.
# Adaptive thinking is on by default on Sonnet 5; it is turned off so every
# representation gets the same, thinking-free treatment.
THINKING = {"type": "disabled"}

_ENC = tiktoken.get_encoding("o200k_base")


def client() -> anthropic.AsyncAnthropic:
    load_dotenv(ROOT / ".env", override=False)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set (environment or .env)")
    # max_retries=0: failures are recorded, never silently retried.
    return anthropic.AsyncAnthropic(max_retries=0, timeout=TIMEOUT_S)


def tiktoken_count(text: str) -> int:
    return len(_ENC.encode(text, disallowed_special=()))


async def count_tokens(api: anthropic.AsyncAnthropic, rep: str, task: dict, page) -> int:
    res = await api.messages.count_tokens(
        model=MODEL,
        system=system_prompt(),
        messages=[{"role": "user", "content": build_user_content(rep, task, page)}],
        thinking=THINKING,
    )
    return res.input_tokens


@dataclass
class CallResult:
    reply_text: str | None
    usage: dict | None
    stop_reason: str | None
    request_id: str | None
    latency_s: float
    error: str | None


async def call_model(api: anthropic.AsyncAnthropic, rep: str, task: dict, page) -> CallResult:
    t0 = time.perf_counter()
    try:
        raw = await api.messages.with_raw_response.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt(),
            messages=[{"role": "user", "content": build_user_content(rep, task, page)}],
            thinking=THINKING,
        )
        msg = raw.parse()
        latency = time.perf_counter() - t0
        text = "".join(b.text for b in msg.content if b.type == "text")
        return CallResult(text, msg.usage.model_dump(), msg.stop_reason, raw.request_id, latency, None)
    except anthropic.APITimeoutError as e:
        return CallResult(None, None, None, None, time.perf_counter() - t0, f"timeout: {e}")
    except anthropic.APIStatusError as e:
        return CallResult(None, None, None, e.request_id, time.perf_counter() - t0,
                          f"api_error {e.status_code}: {e.message[:500]}")
    except anthropic.APIError as e:
        return CallResult(None, None, None, None, time.perf_counter() - t0, f"api_error: {str(e)[:500]}")


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def parse_reply(text: str | None) -> tuple[dict | None, str | None]:
    """Parse the reply per the pre-registered rule; returns (object, error)."""
    if text is None:
        return None, "no_reply"
    s = text.strip()
    m = _FENCE.match(s)
    if m:
        s = m.group(1).strip()
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return None, "malformed_json"
    if not isinstance(obj, dict):
        return None, "malformed_json"
    return obj, None


def reply_rule() -> str:
    return protocol()["reply_parsing"]
