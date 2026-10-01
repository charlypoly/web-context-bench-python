"""Image sizing per Anthropic's vision docs (reference implementation, copied verbatim).

Source: https://platform.claude.com/docs/en/build-with-claude/vision-coordinates
("Resize your image before uploading"), fetched 2026-10-01.
"""

from __future__ import annotations

import math

# Resolution tiers (https://platform.claude.com/docs/en/build-with-claude/vision):
# high-resolution tier (Claude 4.7 and later, including Sonnet 5) and standard tier.
HIGH_RES = {"max_edge": 2576, "max_tokens": 4784}
STANDARD = {"max_edge": 1568, "max_tokens": 1568}


def count_image_tokens(width: int, height: int) -> int:
    """Visual tokens consumed by an image: one token per 28x28 pixel patch."""
    return math.ceil(width / 28) * math.ceil(height / 28)


def resized_size(
    width: int,
    height: int,
    max_edge: int = 1568,
    max_tokens: int = 1568,
) -> tuple[int, int]:
    """The size Claude resizes an image to before padding.

    Defaults are for the standard resolution tier. For high-resolution-tier
    models, use max_edge=2576 and max_tokens=4784. Returns (width, height).
    Images that already fit within the limits are returned unchanged.
    """

    def fits(w: int, h: int) -> bool:
        return (
            math.ceil(w / 28) * 28 <= max_edge
            and math.ceil(h / 28) * 28 <= max_edge
            and count_image_tokens(w, h) <= max_tokens
        )

    if fits(width, height):
        return (width, height)
    if height > width:
        resized_h, resized_w = resized_size(height, width, max_edge, max_tokens)
        return (resized_w, resized_h)

    # Binary search along the long edge for the largest aspect-preserving
    # size that fits.
    aspect_ratio = width / height
    lo, hi = 1, width  # lo always fits; hi never fits
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if fits(mid, max(round(mid / aspect_ratio), 1)):
            lo = mid
        else:
            hi = mid
    return (lo, max(round(lo / aspect_ratio), 1))


def image_accounting(width: int, height: int) -> dict:
    """Dimensions before and after provider-side resizing, padding, and visual tokens, for both tiers."""
    out = {"original": [width, height]}
    for name, tier in (("high_res_tier", HIGH_RES), ("standard_tier", STANDARD)):
        w, h = resized_size(width, height, **tier)
        out[name] = {
            "resized": [w, h],
            "padded": [math.ceil(w / 28) * 28, math.ceil(h / 28) * 28],
            "visual_tokens": count_image_tokens(w, h),
        }
    return out
