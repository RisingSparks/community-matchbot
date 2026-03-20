"""File-based store for raw platform payloads.

Writes one JSON file per scraped item to:
  {base_dir}/{platform}/{YYYY-MM-DD}/{post_id}.json

Files are never overwritten — first write wins.
This lets callers use exists() to cheaply skip re-scraping.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RawStore:
    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir)

    def save(self, platform: str, date: str, post_id: str, payload: dict[str, Any]) -> Path:
        """Persist payload to disk. Skips silently if the file already exists."""
        path = self._path(platform, date, post_id)
        if path.exists():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("RawStore saved %s/%s", platform, post_id)
        return path

    def exists(self, platform: str, post_id: str) -> bool:
        """Return True if any file for this post_id exists under platform/."""
        return self._find(platform, post_id) is not None

    def load(self, platform: str, post_id: str) -> dict[str, Any] | None:
        """Return the saved payload, or None if not found."""
        path = self._find(platform, post_id)
        if path is None:
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_ids(self, platform: str, date: str | None = None) -> list[str]:
        """Return post_ids saved for a platform, optionally filtered to one date.

        Results are sorted by filename (i.e. post_id) for determinism.
        """
        platform_dir = self._base / platform
        if not platform_dir.exists():
            return []
        if date is not None:
            date_dir = platform_dir / date
            if not date_dir.exists():
                return []
            return sorted(p.stem for p in date_dir.glob("*.json"))
        return sorted(p.stem for p in platform_dir.glob("*/*.json"))

    @staticmethod
    def _safe_post_id(post_id: str) -> str:
        """Sanitize post_id to prevent path traversal."""
        return str(post_id).replace("/", "_").replace("\\", "_").replace("..", "_")

    def _path(self, platform: str, date: str, post_id: str) -> Path:
        return self._base / platform / date / f"{self._safe_post_id(post_id)}.json"

    def _find(self, platform: str, post_id: str) -> Path | None:
        """Glob for post_id.json under any date subdirectory."""
        platform_dir = self._base / platform
        if not platform_dir.exists():
            return None
        safe_id = self._safe_post_id(post_id)
        matches = list(platform_dir.glob(f"*/{safe_id}.json"))
        if len(matches) > 1:
            logger.warning("RawStore: post_id %s found in multiple date dirs: %s", post_id, matches)
        return matches[0] if matches else None
