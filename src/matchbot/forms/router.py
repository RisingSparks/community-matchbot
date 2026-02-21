"""
Optional intake form — allows seekers and camps to submit directly
without going through Reddit/Discord/Facebook.

Routes:
  GET  /forms/                 — landing page with links to both forms
  GET  /forms/seeker           — seeker intake form
  POST /forms/seeker           — process seeker submission
  GET  /forms/camp             — camp intake form
  POST /forms/camp             — process camp submission
  GET  /forms/thanks           — confirmation page
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.models import Platform, Post, PostRole, PostStatus, PostType


async def _get_session():
    """FastAPI-compatible async session dependency."""
    from matchbot.db.engine import get_engine
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        yield session

router = APIRouter(prefix="/forms", tags=["intake"])

# ---------------------------------------------------------------------------
# Minimal inline HTML — avoids external template file dependency
# ---------------------------------------------------------------------------

_BASE_CSS = """
body { font-family: system-ui, sans-serif; max-width: 680px; margin: 40px auto; padding: 0 20px; }
h1 { color: #c0392b; }
label { display: block; margin: 12px 0 4px; font-weight: bold; }
input, textarea, select { width: 100%; padding: 8px; box-sizing: border-box; border: 1px solid #ccc; border-radius: 4px; }
button { margin-top: 20px; padding: 10px 24px; background: #c0392b; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; }
.hint { font-size: 12px; color: #666; margin-top: 2px; }
.nav { margin-bottom: 24px; }
.nav a { margin-right: 16px; color: #c0392b; }
"""

_LANDING_HTML = """
<!DOCTYPE html><html><head><title>Matchbot Intake</title>
<style>{css}</style></head><body>
<h1>🔥 Matchbot Intake Forms</h1>
<p>Submit your information to be included in the camp-matching pool for Burning Man.</p>
<div class="nav">
  <a href="/forms/seeker">I'm looking for a camp →</a>
  <a href="/forms/camp">My camp has openings →</a>
</div>
</body></html>
""".format(css=_BASE_CSS)

_SEEKER_FORM_HTML = """
<!DOCTYPE html><html><head><title>Seeker Intake – Matchbot</title>
<style>{css}</style></head><body>
<div class="nav"><a href="/forms/">← Back</a></div>
<h1>🔥 I'm Looking for a Camp</h1>
<form method="post" action="/forms/seeker">
  <label>Your name / handle *</label>
  <input name="display_name" required maxlength="80">

  <label>About you (skills, experience, why you want to burn)</label>
  <textarea name="bio" rows="5" maxlength="2000"></textarea>
  <div class="hint">This becomes the "post body" used for matching.</div>

  <label>Vibes you're looking for (comma-separated)</label>
  <input name="vibes" placeholder="art, build_focused, family_friendly">
  <div class="hint">See taxonomy for valid values.</div>

  <label>What can you contribute? (comma-separated)</label>
  <input name="contributions" placeholder="build, art, kitchen, medic">

  <label>Year (leave blank for current)</label>
  <input name="year" type="number" min="2020" max="2040" placeholder="2026">

  <label>Availability / dates</label>
  <input name="availability_notes" placeholder="Available for build week and the full event">

  <label>How should camps contact you?</label>
  <input name="contact_method" placeholder="DM on Reddit, email, etc.">

  <button type="submit">Submit →</button>
</form>
</body></html>
""".format(css=_BASE_CSS)

_CAMP_FORM_HTML = """
<!DOCTYPE html><html><head><title>Camp Intake – Matchbot</title>
<style>{css}</style></head><body>
<div class="nav"><a href="/forms/">← Back</a></div>
<h1>🔥 My Camp Has Openings</h1>
<form method="post" action="/forms/camp">
  <label>Camp name *</label>
  <input name="camp_name" required maxlength="120">

  <label>Your name / handle (camp contact) *</label>
  <input name="display_name" required maxlength="80">

  <label>About your camp (vibe, activities, expectations)</label>
  <textarea name="bio" rows="5" maxlength="2000"></textarea>
  <div class="hint">This becomes the "post body" used for matching.</div>

  <label>Camp vibes (comma-separated)</label>
  <input name="vibes" placeholder="art, build_focused, dance">

  <label>Roles / contributions you need (comma-separated)</label>
  <input name="contributions" placeholder="build, art, kitchen, sound">

  <label>Approximate camp size</label>
  <input name="camp_size" type="number" min="1" max="5000" placeholder="50">

  <label>Year</label>
  <input name="year" type="number" min="2020" max="2040" placeholder="2026">

  <label>Availability / dates (build week, gate, etc.)</label>
  <input name="availability_notes" placeholder="Looking for early arrival crew">

  <label>How should seekers contact you?</label>
  <input name="contact_method" placeholder="Post in comments, email us at...">

  <button type="submit">Submit →</button>
</form>
</body></html>
""".format(css=_BASE_CSS)

_THANKS_HTML = """
<!DOCTYPE html><html><head><title>Thank you! – Matchbot</title>
<style>{css}</style></head><body>
<h1>🔥 Thank you!</h1>
<p>Your submission has been received and will be reviewed shortly.</p>
<p>If there's a good match, a moderator will reach out to make introductions.</p>
<div class="nav"><a href="/forms/">Submit another →</a></div>
</body></html>
""".format(css=_BASE_CSS)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def intake_landing() -> str:
    return _LANDING_HTML


@router.get("/seeker", response_class=HTMLResponse)
async def seeker_form() -> str:
    return _SEEKER_FORM_HTML


@router.get("/camp", response_class=HTMLResponse)
async def camp_form() -> str:
    return _CAMP_FORM_HTML


@router.get("/thanks", response_class=HTMLResponse)
async def intake_thanks() -> str:
    return _THANKS_HTML


@router.post("/seeker")
async def seeker_submit(
    display_name: Annotated[str, Form()],
    bio: Annotated[str, Form()] = "",
    vibes: Annotated[str, Form()] = "",
    contributions: Annotated[str, Form()] = "",
    year: Annotated[str, Form()] = "",
    availability_notes: Annotated[str, Form()] = "",
    contact_method: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(_get_session),
) -> RedirectResponse:
    title = f"[Intake] Seeker: {display_name}"
    body_parts = []
    if bio:
        body_parts.append(bio)
    if vibes:
        body_parts.append(f"Vibes: {vibes}")
    if contributions:
        body_parts.append(f"Can contribute: {contributions}")
    if availability_notes:
        body_parts.append(f"Availability: {availability_notes}")
    if contact_method:
        body_parts.append(f"Contact: {contact_method}")

    year_int: int | None = None
    try:
        if year.strip():
            year_int = int(year.strip())
    except ValueError:
        pass

    post = Post(
        platform=Platform.MANUAL,
        platform_post_id=f"intake_seeker_{datetime.now(timezone.utc).timestamp()}",
        platform_author_id=display_name,
        author_display_name=display_name,
        source_url="",
        source_community="intake_form",
        title=title,
        raw_text="\n".join(body_parts),
        status=PostStatus.RAW,
        post_type=PostType.MENTORSHIP,
        role=PostRole.SEEKER,
        year=year_int,
        availability_notes=availability_notes or None,
        contact_method=contact_method or None,
    )
    session.add(post)
    await session.commit()

    # Kick off async extraction in background (fire-and-forget)
    _schedule_extraction(post.id)

    return RedirectResponse("/forms/thanks", status_code=303)


@router.post("/camp")
async def camp_submit(
    camp_name: Annotated[str, Form()],
    display_name: Annotated[str, Form()],
    bio: Annotated[str, Form()] = "",
    vibes: Annotated[str, Form()] = "",
    contributions: Annotated[str, Form()] = "",
    camp_size: Annotated[str, Form()] = "",
    year: Annotated[str, Form()] = "",
    availability_notes: Annotated[str, Form()] = "",
    contact_method: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(_get_session),
) -> RedirectResponse:
    title = f"[Intake] Camp: {camp_name}"
    body_parts = [f"Camp: {camp_name}"]
    if bio:
        body_parts.append(bio)
    if vibes:
        body_parts.append(f"Vibes: {vibes}")
    if contributions:
        body_parts.append(f"Looking for: {contributions}")
    if availability_notes:
        body_parts.append(f"Availability: {availability_notes}")
    if contact_method:
        body_parts.append(f"Contact: {contact_method}")

    year_int: int | None = None
    try:
        if year.strip():
            year_int = int(year.strip())
    except ValueError:
        pass

    camp_size_int: int | None = None
    try:
        if camp_size.strip():
            camp_size_int = int(camp_size.strip())
    except ValueError:
        pass

    post = Post(
        platform=Platform.MANUAL,
        platform_post_id=f"intake_camp_{datetime.now(timezone.utc).timestamp()}",
        platform_author_id=display_name,
        author_display_name=display_name,
        source_url="",
        source_community="intake_form",
        title=title,
        raw_text="\n".join(body_parts),
        status=PostStatus.RAW,
        post_type=PostType.MENTORSHIP,
        role=PostRole.CAMP,
        camp_name=camp_name,
        camp_size_min=camp_size_int,
        camp_size_max=camp_size_int,
        year=year_int,
        availability_notes=availability_notes or None,
        contact_method=contact_method or None,
    )
    session.add(post)
    await session.commit()

    _schedule_extraction(post.id)

    return RedirectResponse("/forms/thanks", status_code=303)


def _schedule_extraction(post_id: str) -> None:
    """
    Fire-and-forget LLM extraction for an intake-submitted post.
    Uses asyncio.create_task if a loop is running; otherwise silently skips.
    """
    import asyncio

    async def _run():
        from matchbot.db.engine import get_engine
        from matchbot.extraction import process_post
        from matchbot.extraction.anthropic_extractor import AnthropicExtractor
        from matchbot.extraction.openai_extractor import OpenAIExtractor
        from matchbot.settings import get_settings
        from sqlmodel.ext.asyncio.session import AsyncSession

        settings = get_settings()
        extractor = (
            AnthropicExtractor()
            if settings.llm_provider == "anthropic"
            else OpenAIExtractor()
        )

        async with AsyncSession(get_engine(), expire_on_commit=False) as session:
            post = await session.get(Post, post_id)
            if post:
                await process_post(session, post, extractor)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        pass  # No running loop — extraction will need to be triggered manually
