# Plan: Pre-render Intro Draft at Match Proposal Time

## Context

Currently the intro message is rendered on-the-fly inside `queue send-intro`, shown as a preview,
and the moderator confirms before sending. The moderator never sees the intro during the earlier
review steps (`queue list` / `queue view` / `queue approve`).

The goal: render the intro when the match is *proposed*, store it on the match record, and surface
it in `queue view` so the moderator can read the full drafted message before deciding to approve
or decline — then `send-intro` reuses the stored draft instead of re-rendering.

## Files to change

| File | Change |
|------|--------|
| `src/matchbot/db/models.py` | Add `intro_draft: str \| None = None` field to `Match` |
| `alembic/versions/` | New migration: add `intro_draft` nullable TEXT column to `match` table |
| `src/matchbot/matching/queue.py` | Call `render_intro()` after creating each `Match` and store draft |
| `src/matchbot/cli/cmd_queue.py` | Show `intro_draft` in `queue view` panel |

## Implementation steps

### 1. Add field to Match model (`src/matchbot/db/models.py`)

Add after the existing `mismatch_reason` field:

```python
intro_draft: str | None = Field(default=None)
```

### 2. Create Alembic migration

```bash
uv run alembic revision --autogenerate -m "add intro_draft to match"
uv run alembic upgrade head
```

Verify the generated file adds `intro_draft` as nullable TEXT with no server default.

### 3. Render draft in `propose_matches` (`src/matchbot/matching/queue.py`)

After `session.add(match)` in both `_propose_mentorship_matches` and `_propose_infra_matches`,
import and call `render_intro`:

```python
from matchbot.messaging.renderer import render_intro

try:
    match.intro_draft = render_intro(seeker, camp, seeker.platform)
except Exception:
    pass  # draft is best-effort; don't block match creation
```

Use `seeker.platform` as the platform (same fallback already used in `send-intro`).

### 4. Show draft in `queue view` (`src/matchbot/cli/cmd_queue.py`)

In `queue_view`, append to `panel_content` after the moderator notes section:

```python
f"[bold magenta]Intro draft:[/bold magenta]\n{match.intro_draft or '(not yet rendered)'}\n\n"
```

Place it between the moderator notes block and the SEEKER post text.

### 5. `send-intro` reuses stored draft

In `queue_send_intro`, replace the on-the-fly render:

```python
# Before:
intro_text = render_intro(seeker, camp, target_platform)

# After:
from matchbot.messaging.renderer import render_intro
intro_text = match.intro_draft or render_intro(seeker, camp, target_platform)
```

The fallback ensures old matches (before this change) still work.

## Verification

1. Run existing tests: `uv run pytest tests/ -x -q` — should all pass
2. Submit a test post via CLI (`matchbot submit`) or directly insert a test post
3. Run `matchbot queue list` — confirm match appears as PROPOSED
4. Run `matchbot queue view <id>` — confirm "Intro draft" section shows rendered message text
5. Run `matchbot queue send-intro <id> --dry-run` — confirm same text shown in preview panel
