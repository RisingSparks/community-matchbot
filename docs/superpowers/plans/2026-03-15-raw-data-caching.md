# Raw Data Caching Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist raw platform payloads to disk on first scrape so that data can be re-processed locally without hitting the platform APIs again.

**Architecture:** A `RawStore` class writes one JSON file per scraped item under `data/raw/{platform}/{YYYY-MM-DD}/{post_id}.json`. Each listener calls `RawStore.save()` immediately after fetching and before any processing. A new `matchbot data replay` CLI command reads those files and feeds them back through the existing `process_post()` extraction pipeline.

**Tech Stack:** Python `pathlib` + `json` for file I/O, existing `Typer` CLI (sub-app pattern in `cli/app.py`) for the replay command, existing `process_post()` extraction pipeline for replay.

---

## Chunk 1: RawStore + Settings

### Task 1: Add `raw_data_dir` to Settings

**Files:**
- Modify: `src/matchbot/settings.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_settings.py  (add to existing file, or create if absent)
def test_raw_data_dir_default(reset_settings):
    from matchbot.settings import get_settings
    settings = get_settings()
    assert settings.raw_data_dir == "data/raw"
```

- [x] **Step 2: Run test to verify it fails**

```
uv run pytest tests/test_settings.py::test_raw_data_dir_default -x -q
```
Expected: FAIL — `AttributeError: ... has no attribute 'raw_data_dir'`

- [x] **Step 3: Add field to Settings**

Open `src/matchbot/settings.py`. The `# Storage` section begins at line 66. Add the new field there, after `report_output_dir`:

```python
    report_output_dir: str = Field(default="./reports")
    raw_data_dir: str = Field(default="data/raw", description="Directory for raw platform payload cache")
```

- [x] **Step 4: Run test to verify it passes**

```
uv run pytest tests/test_settings.py::test_raw_data_dir_default -x -q
```
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/matchbot/settings.py tests/test_settings.py
git commit -m "feat: add raw_data_dir setting (default data/raw)"
```

---

### Task 2: Create `RawStore`

**Files:**
- Create: `src/matchbot/storage/__init__.py` (empty)
- Create: `src/matchbot/storage/raw_store.py`
- Create: `tests/test_raw_store.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_raw_store.py
import json
import pytest
from pathlib import Path
from matchbot.storage.raw_store import RawStore


@pytest.fixture
def store(tmp_path):
    return RawStore(base_dir=tmp_path)


def test_save_creates_file(store, tmp_path):
    store.save("reddit", "2026-03-15", "abc123", {"title": "Test post", "selftext": "Hello world"})
    expected = tmp_path / "reddit" / "2026-03-15" / "abc123.json"
    assert expected.exists()
    data = json.loads(expected.read_text())
    assert data["title"] == "Test post"


def test_save_is_idempotent(store, tmp_path):
    store.save("reddit", "2026-03-15", "abc123", {"title": "First"})
    store.save("reddit", "2026-03-15", "abc123", {"title": "Second"})
    # Second save should NOT overwrite
    data = json.loads((tmp_path / "reddit" / "2026-03-15" / "abc123.json").read_text())
    assert data["title"] == "First"


def test_exists_true(store):
    store.save("reddit", "2026-03-15", "abc123", {})
    assert store.exists("reddit", "abc123") is True


def test_exists_false(store):
    assert store.exists("reddit", "missing_id") is False


def test_load_returns_payload(store):
    store.save("reddit", "2026-03-15", "abc123", {"key": "value"})
    result = store.load("reddit", "abc123")
    assert result == {"key": "value"}


def test_load_returns_none_when_missing(store):
    assert store.load("reddit", "missing_id") is None


def test_list_ids_empty(store):
    assert store.list_ids("reddit") == []


def test_list_ids_returns_saved_ids(store):
    store.save("reddit", "2026-03-15", "aaa", {})
    store.save("reddit", "2026-03-15", "bbb", {})
    store.save("discord", "2026-03-15", "ccc", {})
    ids = store.list_ids("reddit")
    assert set(ids) == {"aaa", "bbb"}


def test_list_ids_filtered_by_date(store):
    store.save("reddit", "2026-03-14", "old", {})
    store.save("reddit", "2026-03-15", "new", {})
    ids = store.list_ids("reddit", date="2026-03-15")
    assert ids == ["new"]


def test_list_ids_sorted(store):
    store.save("reddit", "2026-03-15", "zzz", {})
    store.save("reddit", "2026-03-15", "aaa", {})
    ids = store.list_ids("reddit")
    assert ids == ["aaa", "zzz"]
```

- [x] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_raw_store.py -x -q
```
Expected: FAIL — `ModuleNotFoundError: No module named 'matchbot.storage'`

- [x] **Step 3: Create `src/matchbot/storage/__init__.py`**

Empty file — just signals this is a package.

- [x] **Step 4: Implement `raw_store.py`**

```python
# src/matchbot/storage/raw_store.py
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

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, platform: str, date: str, post_id: str, payload: dict[str, Any]) -> Path:
        """Persist payload to disk. Skips silently if the file already exists.

        Args:
            platform: e.g. "reddit", "discord", "facebook"
            date: ISO date string "YYYY-MM-DD" — callers supply today's date
            post_id: platform-specific post identifier (used as filename stem)
            payload: the raw dict from the platform API

        Returns:
            Path where the file was (or would have been) written.
        """
        path = self._path(platform, date, post_id)
        if path.exists():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("RawStore saved %s/%s", platform, post_id)
        return path

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _path(self, platform: str, date: str, post_id: str) -> Path:
        return self._base / platform / date / f"{post_id}.json"

    def _find(self, platform: str, post_id: str) -> Path | None:
        """Glob for post_id.json under any date subdirectory."""
        platform_dir = self._base / platform
        if not platform_dir.exists():
            return None
        matches = list(platform_dir.glob(f"*/{post_id}.json"))
        return matches[0] if matches else None
```

- [x] **Step 5: Run tests to verify they pass**

```
uv run pytest tests/test_raw_store.py -x -q
```
Expected: all PASS

- [x] **Step 6: Commit**

```bash
git add src/matchbot/storage/__init__.py src/matchbot/storage/raw_store.py tests/test_raw_store.py
git commit -m "feat: add RawStore for file-based raw payload caching"
```

---

### Task 3: Add `data/raw/.gitkeep` and update `.gitignore`

- [x] **Step 1: Create the directory placeholder**

```bash
mkdir -p data/raw
touch data/raw/.gitkeep
```

- [x] **Step 2: Add gitignore entry**

Raw data files may contain real user names/post content. The default is to keep them **out of git**. Teams can opt in by removing the gitignore line.

Add to `.gitignore`:

```
# Raw scraped platform data — opt in to commit by removing these lines
# See docs/superpowers/plans/2026-03-15-raw-data-caching.md for details
data/raw/
!data/raw/.gitkeep
```

- [x] **Step 3: Commit**

```bash
git add data/raw/.gitkeep .gitignore
git commit -m "chore: create data/raw/ directory with gitignore opt-out"
```

---

## Chunk 2: Listener Integration

### Task 4: Integrate RawStore into Reddit JSON Listener

**Files:**
- Modify: `src/matchbot/listeners/reddit_json.py`
- Create: `tests/test_reddit_json_raw_store.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_reddit_json_raw_store.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def sample_item():
    return {
        "id": "test123",
        "title": "Looking to join a camp",
        "selftext": "I am interested in joining a camp for BM 2026",
        "author": "redditor_jane",
        "author_fullname": "t2_abc",
        "permalink": "/r/BurningMan/comments/test123/looking_to_join/",
        "created_utc": 1700000000,
    }


@pytest.mark.asyncio
async def test_ingest_saves_raw_payload(tmp_path, sample_item, monkeypatch):
    """Raw payload should be saved to disk before DB processing."""
    from matchbot.storage.raw_store import RawStore
    from matchbot.listeners import reddit_json as rj
    from matchbot.extraction.keywords import KeywordResult

    store = RawStore(base_dir=tmp_path)
    monkeypatch.setattr(rj, "_raw_store", store)
    monkeypatch.setattr(rj, "_post_exists", AsyncMock(return_value=False))

    # Keyword filter returns no_match so we skip DB session complexity
    monkeypatch.setattr(
        rj, "keyword_filter", MagicMock(return_value=KeywordResult(matched=False, candidate_role="unknown", tier="no_match"))
    )

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(rj, "get_session", MagicMock(return_value=mock_ctx))

    await rj._ingest_reddit_json_item(sample_item, extractor=None, dry_run=False)

    # File must exist and contain the full, un-truncated payload
    assert store.exists("reddit", "test123")
    payload = store.load("reddit", "test123")
    assert payload["selftext"] == sample_item["selftext"]
    assert payload["id"] == "test123"


@pytest.mark.asyncio
async def test_ingest_skips_save_when_deduped(tmp_path, sample_item, monkeypatch):
    """Already-seen posts should not be saved again."""
    from matchbot.storage.raw_store import RawStore
    from matchbot.listeners import reddit_json as rj

    store = RawStore(base_dir=tmp_path)
    monkeypatch.setattr(rj, "_raw_store", store)
    monkeypatch.setattr(rj, "_post_exists", AsyncMock(return_value=True))

    outcome, _ = await rj._ingest_reddit_json_item(sample_item, extractor=None, dry_run=False)

    assert outcome == "deduped"
    assert not store.exists("reddit", "test123")
```

- [x] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_reddit_json_raw_store.py -x -q
```
Expected: FAIL — `AttributeError: module has no attribute '_raw_store'`

- [x] **Step 3: Modify `reddit_json.py` to integrate RawStore**

Add near the top (after existing imports):

```python
from datetime import date as _date
from matchbot.storage.raw_store import RawStore

_raw_store: RawStore | None = None


def _get_raw_store() -> RawStore:
    global _raw_store
    if _raw_store is None:
        _raw_store = RawStore(base_dir=get_settings().raw_data_dir)
    return _raw_store
```

In `_ingest_reddit_json_item()`, after the `_post_exists` check and before the `title`/`body` lines, add:

```python
    if await _post_exists(post_id):
        return "deduped", extractor

    # Persist the raw API payload before any transformation or truncation.
    _get_raw_store().save("reddit", _date.today().isoformat(), post_id, data)

    title = (data.get("title") or "")[:500]
    # ... rest of function unchanged ...
```

- [x] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_reddit_json_raw_store.py -x -q
```
Expected: PASS

- [x] **Step 5: Run full test suite to confirm no regressions**

```
uv run pytest tests/ -x -q
```
Expected: all PASS

- [x] **Step 6: Commit**

```bash
git add src/matchbot/listeners/reddit_json.py tests/test_reddit_json_raw_store.py
git commit -m "feat: save raw Reddit JSON payloads to RawStore on ingest"
```

---

### Task 5: Integrate RawStore into Reddit PRAW Listener

**Files:**
- Modify: `src/matchbot/listeners/reddit.py`
- Create: `tests/test_reddit_praw_raw_store.py`

- [x] **Step 1: Read the PRAW listener to find where Post is constructed**

Read `src/matchbot/listeners/reddit.py` and locate the function that processes each submission (likely a loop over `subreddit.stream.submissions()`). Note the exact variable name holding the submission and the dedup check.

- [x] **Step 2: Write the failing test**

```python
# tests/test_reddit_praw_raw_store.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_submission(post_id: str = "praw123") -> MagicMock:
    """Build a minimal mock of an asyncpraw Submission."""
    sub = MagicMock()
    sub.id = post_id
    sub.title = "Seeking camp for 2026"
    sub.selftext = "Full body text here — not truncated"
    sub.author = MagicMock()
    sub.author.__str__ = lambda s: "praw_user"
    sub.author_fullname = "t2_praw"
    sub.permalink = f"/r/BurningMan/comments/{post_id}/"
    sub.url = f"https://reddit.com/r/BurningMan/comments/{post_id}/"
    sub.created_utc = 1700000000.0
    sub.subreddit = MagicMock()
    sub.subreddit.display_name = "BurningMan"
    sub.score = 5
    sub.num_comments = 2
    return sub


@pytest.mark.asyncio
async def test_praw_saves_raw_payload(tmp_path, monkeypatch):
    """PRAW listener should save raw submission fields to RawStore before processing."""
    import matchbot.listeners.reddit as rl
    from matchbot.storage.raw_store import RawStore

    store = RawStore(base_dir=tmp_path)
    monkeypatch.setattr(rl, "_raw_store", store)

    sub = _make_submission()

    # Patch the dedup / DB / extraction layers so we only test the save call.
    # Adjust the exact function names after reading reddit.py in Step 1.
    monkeypatch.setattr(rl, "_post_exists", AsyncMock(return_value=False))

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(rl, "get_session", MagicMock(return_value=mock_ctx))

    # Call the per-submission handler (name found in Step 1 by reading reddit.py).
    # After Step 1, replace this line with the actual function call, e.g.:
    #   await rl._ingest_submission(sub, extractor=None)
    # Do NOT leave this as a comment — the actual call must be uncommented before Step 3.
    raise NotImplementedError("Replace this line with the actual function call from Step 1")

    assert store.exists("reddit", "praw123")
    payload = store.load("reddit", "praw123")
    assert payload["selftext"] == sub.selftext  # full text, no 2000-char truncation
```

> **Note:** After reading `reddit.py` in Step 1, update the test to call the actual per-submission function. The assertions remain the same regardless of function name.

- [x] **Step 3: Run test to verify it fails**

```
uv run pytest tests/test_reddit_praw_raw_store.py -x -q
```
Expected: FAIL

- [x] **Step 4: Add RawStore import and helpers to `reddit.py`**

```python
from datetime import date as _date
from matchbot.storage.raw_store import RawStore

_raw_store: RawStore | None = None


def _get_raw_store() -> RawStore:
    global _raw_store
    if _raw_store is None:
        _raw_store = RawStore(base_dir=get_settings().raw_data_dir)
    return _raw_store


def _submission_to_dict(submission) -> dict:
    """Serialize an asyncpraw Submission to a storable dict (full text, no truncation)."""
    return {
        "id": submission.id,
        "title": submission.title,
        "selftext": submission.selftext,
        "author": str(submission.author) if submission.author else None,
        "author_fullname": getattr(submission, "author_fullname", None),
        "permalink": submission.permalink,
        "url": submission.url,
        "created_utc": submission.created_utc,
        "subreddit": str(submission.subreddit.display_name),
        "score": submission.score,
        "num_comments": submission.num_comments,
    }
```

- [x] **Step 5: Add save call after dedup check**

In the per-submission handler (found in Step 1), immediately after the dedup check, add:

```python
_get_raw_store().save("reddit", _date.today().isoformat(), submission.id, _submission_to_dict(submission))
```

- [x] **Step 6: Run tests to verify they pass**

```
uv run pytest tests/test_reddit_praw_raw_store.py -x -q
```
Expected: PASS

- [x] **Step 7: Run full test suite**

```
uv run pytest tests/ -x -q
```
Expected: all PASS

- [x] **Step 8: Commit**

```bash
git add src/matchbot/listeners/reddit.py tests/test_reddit_praw_raw_store.py
git commit -m "feat: save raw Reddit PRAW submissions to RawStore on ingest"
```

---

### Task 6: Integrate RawStore into Discord Listener

**Files:**
- Modify: `src/matchbot/listeners/discord_bot.py`

- [x] **Step 1: Read the Discord listener**

Read `src/matchbot/listeners/discord_bot.py`. Find `_handle_discord_message` (or equivalent). Note that it already computes `platform_post_id = f"{message.channel.id}_{message.id}"` — reuse this variable rather than recomputing it.

- [x] **Step 2: Add RawStore import and message serialization helper**

```python
from datetime import date as _date
from matchbot.storage.raw_store import RawStore

_raw_store: RawStore | None = None


def _get_raw_store() -> RawStore:
    global _raw_store
    if _raw_store is None:
        _raw_store = RawStore(base_dir=get_settings().raw_data_dir)
    return _raw_store


def _message_to_dict(message) -> dict:
    """Serialize a Discord Message to a storable dict."""
    return {
        "id": str(message.id),
        "channel_id": str(message.channel.id),
        "author_id": str(message.author.id),
        "author_display_name": message.author.display_name,
        "content": message.content,
        "jump_url": message.jump_url,
        "guild_name": message.guild.name if message.guild else None,
        "created_at": message.created_at.isoformat(),
    }
```

- [x] **Step 3: Add save call**

In `_handle_discord_message`, after `platform_post_id` is computed and after any dedup check, add:

```python
# Reuse the existing `platform_post_id` variable — do NOT recompute it.
_get_raw_store().save("discord", _date.today().isoformat(), platform_post_id, _message_to_dict(message))
```

- [x] **Step 4: Run full test suite**

```
uv run pytest tests/ -x -q
```
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/matchbot/listeners/discord_bot.py
git commit -m "feat: save raw Discord messages to RawStore on ingest"
```

---

### Task 7: Integrate RawStore into Facebook Listener

**Files:**
- Modify: `src/matchbot/listeners/facebook.py`

- [x] **Step 1: Read the Facebook listener**

Read `src/matchbot/listeners/facebook.py`. Find the feed processing function. Note the exact `platform_post_id` extraction logic — in the current code it is:

```python
platform_post_id = value.get("post_id") or value.get("id") or f"fb_{uuid.uuid4().hex[:12]}"
```

The priority order (`post_id` before `id`) and the UUID fallback are important to match exactly.

- [x] **Step 2: Add RawStore import**

```python
from datetime import date as _date
from matchbot.storage.raw_store import RawStore

_raw_store: RawStore | None = None


def _get_raw_store() -> RawStore:
    global _raw_store
    if _raw_store is None:
        _raw_store = RawStore(base_dir=get_settings().raw_data_dir)
    return _raw_store
```

- [x] **Step 3: Add save call in the feed processing function**

After `platform_post_id` is computed, add a save call — but **only when post_id is not UUID-generated**, because UUID-based IDs are random and can't be correlated on replay:

```python
# Save only when we have a stable platform-provided ID.
# UUID-generated fallback IDs (fb_...) are random and cannot be replayed reliably.
stable_post_id = value.get("post_id") or value.get("id")
if stable_post_id:
    _get_raw_store().save("facebook", _date.today().isoformat(), stable_post_id, value)
```

- [x] **Step 4: Run full test suite**

```
uv run pytest tests/ -x -q
```
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/matchbot/listeners/facebook.py
git commit -m "feat: save raw Facebook webhook payloads to RawStore on ingest"
```

---

## Chunk 3: Replay CLI Command

### Task 8: Create `matchbot data replay` Command

The replay command reads raw files from `data/raw/` and re-runs each payload through the same extraction pipeline that live listeners use. Posts already in the DB (by `platform_post_id`) are skipped.

**Files:**
- Create: `src/matchbot/cli/cmd_data.py` (naming matches existing pattern: `cmd_posts.py`, `cmd_queue.py`, etc.)
- Modify: `src/matchbot/cli/app.py` (wire up `data` sub-app)
- Create: `tests/test_cli_data.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_cli_data.py
import json
import pytest
from pathlib import Path
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock

from matchbot.cli.app import app


runner = CliRunner(mix_stderr=False)


@pytest.fixture
def raw_dir(tmp_path):
    """Populate a temp data/raw dir with one Reddit post."""
    post = {
        "id": "abc123",
        "title": "Looking for camp",
        "selftext": "I want to join a theme camp for BM 2026.",
        "author": "testuser",
        "author_fullname": "t2_xyz",
        "permalink": "/r/BurningMan/comments/abc123/",
        "created_utc": 1700000000,
    }
    post_dir = tmp_path / "reddit" / "2026-03-15"
    post_dir.mkdir(parents=True)
    (post_dir / "abc123.json").write_text(json.dumps(post))
    return tmp_path


def test_data_replay_help():
    result = runner.invoke(app, ["data", "replay", "--help"])
    assert result.exit_code == 0
    assert "--platform" in result.output


def test_data_replay_dry_run(raw_dir, monkeypatch):
    """Dry-run should list posts that would be processed without touching the DB."""
    monkeypatch.setenv("RAW_DATA_DIR", str(raw_dir))

    # Patch _post_exists_batch so no real DB connection is made
    with patch("matchbot.cli.cmd_data._post_exists_batch", return_value={"abc123": False}):
        result = runner.invoke(app, ["data", "replay", "--platform", "reddit", "--dry-run"])

    assert result.exit_code == 0
    assert "abc123" in result.output
    assert "would process" in result.output.lower() or "dry" in result.output.lower()


def test_data_replay_skips_existing_db_post(raw_dir, monkeypatch):
    """Posts already in DB should be skipped, not re-processed."""
    monkeypatch.setenv("RAW_DATA_DIR", str(raw_dir))

    with patch("matchbot.cli.cmd_data._post_exists_batch", return_value={"abc123": True}):
        result = runner.invoke(app, ["data", "replay", "--platform", "reddit"])

    assert result.exit_code == 0
    assert "skipped" in result.output.lower()


def test_data_replay_unknown_platform(raw_dir, monkeypatch):
    monkeypatch.setenv("RAW_DATA_DIR", str(raw_dir))
    result = runner.invoke(app, ["data", "replay", "--platform", "twitter"])
    assert result.exit_code != 0
```

- [x] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_cli_data.py -x -q
```
Expected: FAIL — `data` group not found

- [x] **Step 3: Implement `src/matchbot/cli/cmd_data.py`**

```python
# src/matchbot/cli/cmd_data.py
"""CLI commands for raw data management and replay."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import typer

from matchbot.settings import get_settings
from matchbot.storage.raw_store import RawStore

app = typer.Typer(help="Raw data management commands.")
logger = logging.getLogger(__name__)

_PLATFORM_MAP = {
    "reddit": "reddit",
    "discord": "discord",
    "facebook": "facebook",
}


def _get_raw_store() -> RawStore:
    return RawStore(base_dir=get_settings().raw_data_dir)


async def _post_exists_async(platform: str, post_ids: list[str]) -> dict[str, bool]:
    """Return a mapping of post_id → True if already in DB."""
    from sqlmodel import select
    from matchbot.db.engine import get_session
    from matchbot.db.models import Post

    async with get_session() as session:
        rows = (
            await session.exec(
                select(Post.platform_post_id).where(
                    Post.platform == platform,
                    Post.platform_post_id.in_(post_ids),
                )
            )
        ).all()
    existing = set(rows)
    return {pid: pid in existing for pid in post_ids}


def _post_exists_batch(platform: str, post_ids: list[str]) -> dict[str, bool]:
    """Synchronous wrapper — runs one DB query for all IDs at once."""
    return asyncio.run(_post_exists_async(platform, post_ids))


async def _replay_one(platform: str, post_id: str, payload: dict) -> None:
    """Reconstruct a Post from a raw payload and run extraction.

    NOTE: This function imports private helpers from listener modules
    (_build_source_url, _source_created_at_from_json) to keep the mapping
    logic in sync with how listeners construct Post objects. If those helpers
    are renamed or moved, update the imports here.
    """
    from matchbot.db.engine import get_session
    from matchbot.db.models import Post, PostStatus
    from matchbot.extraction import process_post
    from matchbot.extraction.anthropic_extractor import AnthropicExtractor
    from matchbot.extraction.openai_extractor import OpenAIExtractor

    settings = get_settings()

    if platform == "reddit":
        from matchbot.listeners.reddit_json import (
            _build_source_url,
            _source_created_at_from_json,
            _REDDIT_COMMUNITY,
        )
        title = (payload.get("title") or "")[:500]
        raw_text = (payload.get("selftext") or "")[:2000]
        author_id = payload.get("author_fullname") or payload.get("author") or "unknown"
        author_display = payload.get("author") or author_id
        source_url = _build_source_url(payload.get("permalink") or payload.get("url") or "")
        source_community = payload.get("subreddit") or _REDDIT_COMMUNITY
        source_created_at = _source_created_at_from_json(payload)

    elif platform == "discord":
        title = (payload.get("content") or "")[:80]
        raw_text = (payload.get("content") or "")[:2000]
        author_id = payload.get("author_id") or ""
        author_display = payload.get("author_display_name") or ""
        source_url = payload.get("jump_url") or ""
        source_community = f"Discord: {payload.get('guild_name') or ''}"
        source_created_at = None

    else:  # facebook
        title = (payload.get("message") or "")[:80]
        raw_text = (payload.get("message") or "")[:2000]
        author_id = (payload.get("from") or {}).get("id") or ""
        author_display = (payload.get("from") or {}).get("name") or ""
        source_url = payload.get("permalink_url") or ""
        source_community = f"Facebook Group: {payload.get('group_id') or ''}"
        source_created_at = None

    post = Post(
        platform=platform,
        platform_post_id=post_id,
        platform_author_id=author_id,
        author_display_name=author_display,
        source_url=source_url,
        source_community=source_community,
        title=title,
        raw_text=raw_text,
        source_created_at=source_created_at,
        status=PostStatus.RAW,
    )

    extractor = AnthropicExtractor() if settings.llm_provider != "openai" else OpenAIExtractor()
    try:
        async with get_session() as session:
            session.add(post)
            await session.commit()
            await session.refresh(post)
            await process_post(session, post, extractor, on_extraction_error="raw")
    finally:
        await extractor.aclose()


@app.command()
def replay(
    platform: str = typer.Option(..., help="Platform to replay: reddit, discord, facebook"),
    date: Optional[str] = typer.Option(None, help="Replay only this date (YYYY-MM-DD). Default: all dates."),
    dry_run: bool = typer.Option(False, "--dry-run", help="List what would be processed without touching the DB."),
) -> None:
    """Re-process raw cached payloads through the extraction pipeline.

    Reads raw JSON files from the data/raw/ directory and feeds each one
    through the same extraction pipeline used by live listeners.
    Posts already in the database are skipped.
    """
    if platform not in _PLATFORM_MAP:
        valid = ", ".join(_PLATFORM_MAP)
        typer.echo(f"Error: Unknown platform '{platform}'. Valid: {valid}", err=True)
        raise typer.Exit(code=1)

    store = _get_raw_store()
    ids = store.list_ids(platform, date=date)

    if not ids:
        typer.echo(f"No raw files found for platform={platform}" + (f" date={date}" if date else "") + ".")
        raise typer.Exit()

    typer.echo(f"Found {len(ids)} raw file(s) for {platform}" + (f" on {date}" if date else "") + ".")

    # Batch DB lookup — one query for all IDs instead of N queries.
    exists_map = _post_exists_batch(platform, ids)

    async def _run_all() -> tuple[int, int, int]:
        processed = skipped = errors = 0
        for post_id in ids:
            if exists_map.get(post_id):
                typer.echo(f"  [skipped] {post_id} — already in DB")
                skipped += 1
                continue

            payload = store.load(platform, post_id)
            if payload is None:
                typer.echo(f"  [error] {post_id} — file missing or unreadable")
                errors += 1
                continue

            if dry_run:
                typer.echo(f"  [would process] {post_id}")
                processed += 1
                continue

            try:
                await _replay_one(platform, post_id, payload)
                typer.echo(f"  [processed] {post_id}")
                processed += 1
            except Exception as exc:  # noqa: BLE001
                typer.echo(f"  [error] {post_id} — {exc}")
                errors += 1

        return processed, skipped, errors

    processed, skipped, errors = asyncio.run(_run_all())
    typer.echo(f"\nDone. processed={processed} skipped={skipped} errors={errors}")
```

> **Design note:** `asyncio.run()` is called once at the top level wrapping the full replay loop, not per-item. This avoids creating/destroying an event loop on every post, and is safe for a CLI context (no pre-existing event loop).

- [x] **Step 4: Wire up in `src/matchbot/cli/app.py`**

```python
# Add with the other imports:
from matchbot.cli.cmd_data import app as data_app

# Add with the other add_typer calls:
app.add_typer(data_app, name="data", help="Raw data caching and replay")
```

- [x] **Step 5: Run tests**

```
uv run pytest tests/test_cli_data.py -x -q
```
Expected: PASS

- [x] **Step 6: Smoke-test CLI manually**

```
uv run matchbot data --help
uv run matchbot data replay --help
```
Expected: help text with `--platform`, `--date`, `--dry-run` options.

- [x] **Step 7: Run full test suite**

```
uv run pytest tests/ -x -q
```
Expected: all PASS

- [x] **Step 8: Commit**

```bash
git add src/matchbot/cli/cmd_data.py src/matchbot/cli/app.py tests/test_cli_data.py
git commit -m "feat: add matchbot data replay CLI for replaying cached raw payloads"
```

---

## Chunk 4: Cache-First Backfill

### Task 9: Make `backfill_reddit_json.py` Cache-First by Default

**Default behavior:** if `data/raw/reddit/` has any files for dates >= `--since-date`, process from cache — no Reddit API calls. Add `--live` to force Reddit regardless.

**First-run:** cache is empty → automatically falls through to Reddit API (no flag needed).
**Subsequent runs:** cache is populated → uses cache by default; logs a message explaining why.

This inverts the old design (opt-in `--from-cache`) to opt-out (`--live`), which is the correct default because re-scraping should require explicit intent.

**Files:**
- Modify: `scripts/backfill_reddit_json.py`

**Reuse rule:** Do NOT duplicate `_replay_one()` or `_post_exists_batch()`. Import them directly from `matchbot.cli.cmd_data`.

- [x] **Step 1: Read `scripts/backfill_reddit_json.py` and `src/matchbot/cli/cmd_data.py`**

Understand the current `main()` / `_main_async()` structure and which symbols to import from `cmd_data`.

- [x] **Step 2: Add `--live` option to `main()`**

```python
live: bool = typer.Option(
    False,
    "--live",
    help="Force fetching from the Reddit API even if a local cache exists.",
),
```

Pass it through to `_main_async()`.

- [x] **Step 3: Implement cache-first auto-detection in `_main_async()`**

After the `reset_db` / `create_db_and_tables()` block, add:

```python
if not live:
    cached_ids = _collect_cached_ids(since_datetime, settings=get_settings())
    if cached_ids:
        logger.info(
            "Cache-first: found %d cached post(s) for dates >= %s. "
            "Processing from cache. Pass --live to fetch from Reddit instead.",
            len(cached_ids),
            since_datetime.date(),
        )
        await _backfill_from_cache(cached_ids, dry_run=dry_run)
        await dispose_engine()
        return
    logger.info("Cache empty for dates >= %s — fetching from Reddit.", since_datetime.date())
```

Then implement the two helpers:

```python
def _collect_cached_ids(since_datetime: datetime, *, settings) -> list[str]:
    """Return all post IDs in data/raw/reddit/ for scrape-dates >= since_datetime.date()."""
    from matchbot.storage.raw_store import RawStore

    store = RawStore(base_dir=settings.raw_data_dir)
    since_date = since_datetime.date()
    platform_dir = Path(settings.raw_data_dir) / "reddit"
    all_ids: list[str] = []
    if not platform_dir.exists():
        return all_ids
    for date_dir in sorted(platform_dir.iterdir()):
        try:
            dir_date = datetime.strptime(date_dir.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if dir_date >= since_date:
            all_ids.extend(store.list_ids("reddit", date=date_dir.name))
    return all_ids


async def _backfill_from_cache(all_ids: list[str], *, dry_run: bool) -> None:
    """Replay raw Reddit payloads from disk without hitting the Reddit API."""
    from matchbot.storage.raw_store import RawStore
    from matchbot.cli.cmd_data import _post_exists_batch, _replay_one
    from matchbot.settings import get_settings

    settings = get_settings()
    store = RawStore(base_dir=settings.raw_data_dir)
    exists_map = _post_exists_batch("reddit", all_ids)

    processed = skipped = errors = 0
    for post_id in all_ids:
        if exists_map.get(post_id):
            logger.debug("Cache replay: skipping %s (already in DB)", post_id)
            skipped += 1
            continue

        payload = store.load("reddit", post_id)
        if payload is None:
            logger.warning("Cache replay: file missing for %s", post_id)
            errors += 1
            continue

        if dry_run:
            logger.info("Cache replay [dry-run]: would process %s", post_id)
            processed += 1
            continue

        try:
            await _replay_one("reddit", post_id, payload)
            logger.info("Cache replay: processed %s", post_id)
            processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("Cache replay: error on %s — %s", post_id, exc)
            errors += 1

    logger.info(
        "Cache replay complete: processed=%d skipped=%d errors=%d dry_run=%s",
        processed, skipped, errors, dry_run,
    )
```

- [x] **Step 4: Guard `--live` with API-only flags**

When `--live` is NOT set, `--fetch-limit`, `--sleep-seconds`, and `--max-pages` are irrelevant (cache path runs instead). Warn if they're set alongside the implicit cache path:

```python
if not live and cached_ids and (fetch_limit or sleep_seconds != 1.5 or max_pages != 500):
    logger.warning(
        "Using cache (--live not set): --fetch-limit, --sleep-seconds, and --max-pages are ignored."
    )
```

Place this warning before the `await _backfill_from_cache(...)` call.

- [x] **Step 5: Smoke-test manually**

```bash
# First run (empty cache) — should hit Reddit as before:
python scripts/backfill_reddit_json.py --since-date 2026-01-01 --dry-run

# After cache is populated — should use cache automatically:
python scripts/backfill_reddit_json.py --since-date 2026-01-01 --dry-run
# Expected log: "Cache-first: found N cached post(s)..."

# Force Reddit even with populated cache:
python scripts/backfill_reddit_json.py --since-date 2026-01-01 --live --dry-run
```

- [x] **Step 6: Run full test suite**

```
uv run pytest tests/ -x -q
```

Expected: all PASS.

- [x] **Step 7: Commit**

```bash
git add scripts/backfill_reddit_json.py
git commit -m "feat: make backfill cache-first by default; add --live to force Reddit API"
```

---

## Summary

After all tasks complete, the feature works as follows:

**On live ingest:** Each listener saves the full raw API payload to `data/raw/{platform}/{today}/{post_id}.json` before any DB work. Files are never overwritten (first-write-wins).

**To re-process without re-scraping:**

```bash
# Replay all cached Reddit posts
uv run matchbot data replay --platform reddit

# Replay only posts fetched on a specific date
uv run matchbot data replay --platform reddit --date 2026-03-15

# Dry-run to preview what would be processed
uv run matchbot data replay --platform reddit --dry-run
```

**Backfill is cache-first by default:**

```bash
# First run (empty cache) — hits Reddit, saves to cache:
python scripts/backfill_reddit_json.py --since-date 2026-01-01

# Subsequent runs (cache populated) — uses cache automatically, no Reddit API calls:
python scripts/backfill_reddit_json.py --since-date 2026-01-01

# Force Reddit even with a populated cache (e.g. to pick up new posts):
python scripts/backfill_reddit_json.py --since-date 2026-01-01 --live
```

If `data/raw/reddit/` has any files for scrape-dates >= `--since-date`, the script uses those automatically and logs `"Cache-first: found N cached post(s)..."`. Pass `--live` to override and hit Reddit regardless.

**To commit raw data to git (opt-in):** Remove the `data/raw/` entry from `.gitignore`. Be aware this commits real user-generated content (usernames, post text).

**Facebook caveat:** Posts with no stable platform ID (UUID fallback) are not saved to disk, because random IDs cannot be correlated on replay.

**Private import note:** `_replay_one` in `cmd_data.py` imports private helpers (`_build_source_url`, `_source_created_at_from_json`) from `reddit_json.py`. If those are ever renamed, update `cmd_data.py` accordingly.
