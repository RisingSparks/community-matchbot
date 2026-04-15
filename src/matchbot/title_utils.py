"""Helpers for deriving compact human-readable post titles."""

from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_line(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _truncate(candidate: str, *, max_len: int) -> str:
    if len(candidate) > max_len:
        truncated = candidate[: max_len + 1].rsplit(" ", 1)[0].strip()
        candidate = truncated or candidate[:max_len].strip()
    return candidate[:max_len]


def build_post_title(raw_text: str, *, max_len: int = 80) -> str:
    """Derive a short title from post text, preferring the first meaningful line."""
    if not raw_text:
        return ""

    lines = [_normalize_line(line) for line in raw_text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""

    return _truncate(lines[0], max_len=max_len)


def build_source_title(source_title: str, raw_text: str, *, max_len: int = 80) -> str:
    """Apply the same ingest-time title selection logic across platforms."""
    normalized_source = _normalize_line(source_title)
    if normalized_source:
        return _truncate(normalized_source, max_len=max_len)
    return build_post_title(raw_text, max_len=max_len)
