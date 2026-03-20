# Plan: Fix feedback survey, opt-out handling, and tag pollution

## Context

Three gaps were identified in a code review:
1. **Opt-out is a broken promise** — all 9 intro templates tell recipients to reply "opt out" but no listener handles that reply.
2. **Feedback survey is a stub** — the scheduler flags `[feedback pending]` on matches but never sends anything and there's no CLI to action them.
3. **`[feedback pending]` tag pollutes moderator notes** — tags accumulate with no way to clear them.

User choices: opt-out uses a simple blocklist table; feedback is full-send (message sent + CLI commands).

---

## Issue 1: Opt-Out Handling

### New model: `OptOut`
**File**: `src/matchbot/db/models.py`

Add after the `Event` class:
```python
class OptOut(SQLModel, table=True):
    __tablename__ = "opt_out"
    id: str = Field(default_factory=_new_id, primary_key=True)
    platform: str = Field(index=True)
    platform_author_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=_now)
```

### Helper function
**File**: `src/matchbot/db/models.py` (or a new `src/matchbot/db/optout.py`)

```python
async def is_opted_out(session: AsyncSession, platform: str, author_id: str) -> bool:
    result = (await session.exec(
        select(OptOut).where(
            OptOut.platform == platform,
            OptOut.platform_author_id == author_id,
        )
    )).first()
    return result is not None
```

### Queue check
**File**: `src/matchbot/matching/queue.py`

In both `_propose_mentorship_matches` and `_propose_infra_matches`, add an opt-out check in the candidate loop (after the deduplication check, before scoring):
```python
if await is_opted_out(session, candidate.platform, candidate.platform_author_id):
    continue
```
Also check `new_post` before the loop starts (if new_post author opted out, return `[]`).

### Discord DM handler
**File**: `src/matchbot/listeners/discord_bot.py`

In `on_message`, DMs have `message.guild is None`. Add a branch before `_handle_discord_message` is called:
```python
if message.guild is None:
    if message.content.strip().lower() == "opt out":
        await _handle_opt_out_discord(message)
    return  # don't ingest DMs as posts
```

New function `_handle_opt_out_discord(message)`:
- Open DB session, create `OptOut(platform=Platform.DISCORD, platform_author_id=str(message.author.id))`
- Send confirmation DM reply: "You've been opted out of future introductions. You won't receive any more match messages from us."

### Reddit inbox listener
**File**: `src/matchbot/listeners/reddit.py`

Add a new coroutine `run_reddit_inbox_listener()` that:
- Creates an asyncpraw Reddit client
- Streams `reddit.inbox.stream()` (unread messages)
- For each message: if `message.body.strip().lower() == "opt out"` (or contains it), create `OptOut(platform=Platform.REDDIT, platform_author_id=str(message.author))`, mark message as read, reply with opt-out confirmation
- Has the same reconnect/backoff logic as `run_reddit_listener`

The server startup (`src/matchbot/server.py`) needs to launch both `run_reddit_listener` and `run_reddit_inbox_listener` as concurrent tasks.

### Facebook webhook handler
**File**: `src/matchbot/forms/router.py`

Facebook sends `messages` events to the same webhook endpoint. Add handling in the existing webhook POST handler for `field == "messages"`:
- Extract `sender_id` from `value["sender"]["id"]` and `text` from `value["message"]["text"]`
- If `text.strip().lower() == "opt out"`, create `OptOut(platform=Platform.FACEBOOK, platform_author_id=sender_id)`
- Optionally send a Facebook message reply via `_send_fb_message()` (imported from `sender_facebook.py`)

---

## Issue 2: Feedback Survey (full send)

### New templates
**Directory**: `src/matchbot/config/templates/`

Create three files (`feedback_reddit.md.j2`, `feedback_discord.md.j2`, `feedback_facebook.md.j2`):
- Short (3–5 lines): remind who they were connected with, ask if it led anywhere, include opt-out reminder
- Context variables: `username`, `other_party`, `moderator_name`

Example content:
```
Hi {{ username }}, it's been a couple of weeks since we introduced you to {{ other_party }}.

Did the connection lead anywhere? We'd love to know — it helps us improve the matchmaking.

Just reply to share, or ignore this if you'd prefer not to.

— {{ moderator_name }} (reply "opt out" to stop receiving these)
```

### Renderer
**File**: `src/matchbot/messaging/renderer.py`

Add a new function:
```python
def render_feedback(post: Post, other_post: Post, platform: str) -> str:
    """Render a feedback follow-up message for a match participant."""
```
Template lookup: `feedback_{platform}.md.j2`. Context: `username` (from `post`), `other_party` (from `other_post`), `moderator_name`.

### Messaging dispatcher
**File**: `src/matchbot/messaging/__init__.py`

Add:
```python
async def send_feedback_message(
    session: AsyncSession,
    match: Match,
    seeker: Post,
    camp: Post,
) -> None:
```
- Uses `match.intro_platform` to determine platform
- Renders via `render_feedback(seeker, camp, platform)` for seeker, `render_feedback(camp, seeker, platform)` for camp
- Calls the appropriate platform sender (can reuse the `_send_*` helpers from the sender modules, or add simple send functions)
- Only sends to participants whose platform matches `intro_platform` (avoid cross-platform sending)

### CLI commands
**File**: `src/matchbot/cli/cmd_queue.py`

**`queue feedback-list`**:
```
@app.command("feedback-list")
def queue_feedback_list(limit: int = 25) -> None:
    """List matches with feedback pending."""
```
- Queries all INTRO_SENT matches where `moderator_notes` contains `[feedback pending]`
- Renders a Rich table (same style as `queue_list`)

**`queue send-feedback`**:
```
@app.command("send-feedback")
def queue_send_feedback(
    match_id: str,
    dry_run: bool = False,
) -> None:
    """Send feedback follow-up message and clear the [feedback pending] tag."""
```
- Loads match, validates `[feedback pending]` is in notes
- Renders preview of feedback messages for both seeker and camp
- Confirms before sending (unless `--dry-run`)
- Calls `send_feedback_message(session, match, seeker, camp)`
- Strips `[feedback pending]` from `moderator_notes`, commits

---

## Issue 3: Tag pollution

Resolved automatically by `send-feedback`: stripping `[feedback pending]` from `moderator_notes` after sending. No other changes needed to the scheduler.

---

## Files to modify

| File | Change |
|------|--------|
| `src/matchbot/db/models.py` | Add `OptOut` model + `is_opted_out()` helper |
| `src/matchbot/matching/queue.py` | Opt-out check in both propose functions |
| `src/matchbot/listeners/discord_bot.py` | Handle DM "opt out", skip DMs as posts |
| `src/matchbot/listeners/reddit.py` | Add `run_reddit_inbox_listener()` coroutine |
| `src/matchbot/server.py` | Start inbox listener alongside submission listener |
| `src/matchbot/forms/router.py` | Handle Facebook `messages` webhook field |
| `src/matchbot/messaging/renderer.py` | Add `render_feedback()` |
| `src/matchbot/messaging/__init__.py` | Add `send_feedback_message()` |
| `src/matchbot/cli/cmd_queue.py` | Add `feedback-list` and `send-feedback` commands |

## Files to create

| File | Purpose |
|------|---------|
| `src/matchbot/config/templates/feedback_reddit.md.j2` | Reddit feedback template |
| `src/matchbot/config/templates/feedback_discord.md.j2` | Discord feedback template |
| `src/matchbot/config/templates/feedback_facebook.md.j2` | Facebook feedback template |

---

## Verification

1. **Opt-out model**: `uv run pytest tests/` — existing tests still pass; add test that `is_opted_out()` returns True after insert and that `propose_matches` skips opted-out authors.
2. **Discord opt-out**: Unit test `_handle_opt_out_discord` by mocking `get_session` and a fake `discord.Message` with `guild=None` and content `"opt out"`.
3. **Reddit inbox**: Test `run_reddit_inbox_listener` by mocking asyncpraw inbox stream with a fake message.
4. **Feedback CLI**: `matchbot queue feedback-list` shows `[feedback pending]` matches; `matchbot queue send-feedback <id> --dry-run` shows preview without sending.
5. **Feedback send**: Integration test mocking the platform sender; verify `[feedback pending]` is removed from notes after `send-feedback`.
