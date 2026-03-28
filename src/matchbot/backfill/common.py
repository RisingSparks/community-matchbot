"""Common count and progress helpers for backfill flows."""

from __future__ import annotations

import logging
import time
from typing import Any

_DEFAULT_COUNT_KEYS = (
    "fetched",
    "new_candidates",
    "deduped",
    "before_cutoff",
    "matched",
    "skipped",
    "extracted",
    "raw_after_error",
)


def new_backfill_counts(*, extra_keys: tuple[str, ...] = ()) -> dict[str, int]:
    counts = {key: 0 for key in _DEFAULT_COUNT_KEYS}
    for key in extra_keys:
        counts.setdefault(key, 0)
    return counts


def accumulate_counts(total: dict[str, int], batch_counts: dict[str, int]) -> None:
    for key in total:
        total[key] += batch_counts.get(key, 0)


def should_log_progress(processed: int, total: int, *, every: int) -> bool:
    if processed <= 0:
        return False
    return processed == 1 or processed == total or processed % every == 0


def log_backfill_progress(
    logger: logging.Logger,
    *,
    label: str,
    counts: dict[str, int],
    started_at: float,
    processed: int | None = None,
    total: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    elapsed = time.monotonic() - started_at
    parts: list[str] = [f"{label} progress:"]
    if processed is not None and total is not None:
        parts.append(f"{processed}/{total} processed")
    for key in (
        "pages",
        "fetched",
        "new_candidates",
        "deduped",
        "before_cutoff",
        "matched",
        "skipped",
        "extracted",
        "raw_after_error",
    ):
        if key in counts:
            parts.append(f"{key}={counts[key]}")
    if extra:
        for key, value in extra.items():
            parts.append(f"{key}={value!r}")
    parts.append(f"elapsed={elapsed:.1f}s")
    logger.info(" ".join(parts))
