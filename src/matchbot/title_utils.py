"""Helpers for deriving compact human-readable post titles."""

from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_line(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def build_post_title(raw_text: str, *, max_len: int = 80) -> str:
    """Derive a short title from post text, preferring the first meaningful line."""
    if not raw_text:
        return ""

    lines = [_normalize_line(line) for line in raw_text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""

    candidate = lines[0]
    if len(candidate) > max_len:
        truncated = candidate[: max_len + 1].rsplit(" ", 1)[0].strip()
        candidate = truncated or candidate[:max_len].strip()
    return candidate[:max_len]
