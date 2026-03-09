"""
Optional intake form — allows seekers, camps, and infra requests/offers to
submit directly without going through Reddit/Discord/Facebook.

Routes:
  GET  /forms/                 — landing page with links to forms
  GET  /forms/seeker           — seeker intake form
  POST /forms/seeker           — process seeker submission
  GET  /forms/camp             — camp intake form
  POST /forms/camp             — process camp submission
  GET  /forms/infra            — infrastructure intake form
  POST /forms/infra            — process infrastructure submission
  GET  /forms/thanks           — confirmation page
"""

from __future__ import annotations

from datetime import UTC, datetime
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
.disclaimer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #888; line-height: 1.4; }
"""

_DISCLAIMER_HTML = """
<div class="disclaimer">
  Rising Sparks is a volunteer-led community experiment. While we collaborate with folks across 
  the ecosystem, this is not an official Burning Man Project initiative.
</div>
"""

_LANDING_HTML = f"""
<!DOCTYPE html><html><head><title>Rising Sparks Pool</title>
<style>{_BASE_CSS}</style></head><body>
<h1>Join the Rising Sparks Pool</h1>
<p>We help self-motivated people find aligned communities where they can contribute and learn. 
Tell us about yourself or your project to get started.</p>
<div class="nav">
  <a href="/forms/seeker">I want to contribute & learn →</a>
  <a href="/forms/camp">We’re looking for builders & collaborators →</a>
  <a href="/forms/infra">We need or can offer infrastructure →</a>
</div>
{_DISCLAIMER_HTML}
</body></html>
"""

_SEEKER_FORM_HTML = f"""
<!DOCTYPE html><html><head><title>Find Your Community – Rising Sparks</title>
<style>{_BASE_CSS}</style></head><body>
<div class="nav"><a href="/forms/">← Back</a></div>
<h1>I want to contribute & learn</h1>
<form method="post" action="/forms/seeker">
  <label>How should we call you? *</label>
  <input name="display_name" required maxlength="80">

  <label>What are you building? (Tell us about your skills, your experience, and what draws you to the dust.)</label>
  <textarea name="bio" rows="5" maxlength="2000"></textarea>
  <div class="hint">This helps our moderators understand your contribution style.</div>

  <label>Vibes you're looking for (comma-separated)</label>
  <input name="vibes" placeholder="art, build_focused, family_friendly">
  <div class="hint">e.g. sober, loud, late-night, workshop, wellness</div>

  <label>What can you contribute? (comma-separated)</label>
  <input name="contributions" placeholder="build, art, kitchen, medic">

  <label>Year (leave blank for current)</label>
  <input name="year" type="number" min="2020" max="2040" placeholder="2026">

  <label>Availability / dates</label>
  <input name="availability_notes" placeholder="e.g. Available for build week and the full event">

  <label>How should potential matches contact you?</label>
  <input name="contact_method" placeholder="DM on Reddit, email, etc.">

  <button type="submit">Join the Pool →</button>
</form>
{_DISCLAIMER_HTML}
</body></html>
"""

_CAMP_FORM_HTML = f"""
<!DOCTYPE html><html><head><title>Find Your Builders – Rising Sparks</title>
<style>{_BASE_CSS}</style></head><body>
<div class="nav"><a href="/forms/">← Back</a></div>
<h1>We’re looking for builders & collaborators</h1>
<form method="post" action="/forms/camp">
  <label>Camp or Art Project name *</label>
  <input name="camp_name" required maxlength="120">

  <label>Your name / handle (project contact) *</label>
  <input name="display_name" required maxlength="80">

  <label>Tell us about your project (Describe your vibe, what you build, and what you expect from collaborators.)</label>
  <textarea name="bio" rows="5" maxlength="2000"></textarea>
  <div class="hint">This helps self-motivated seekers find your project.</div>

  <label>Project vibes (comma-separated)</label>
  <input name="vibes" placeholder="art, build_focused, dance">

  <label>Who are you looking for? (roles/skills, comma-separated)</label>
  <input name="contributions" placeholder="build, art, kitchen, sound">

  <label>Approximate group size</label>
  <input name="camp_size" type="number" min="1" max="5000" placeholder="50">

  <label>Year</label>
  <input name="year" type="number" min="2020" max="2040" placeholder="2026">

  <label>Availability / dates (build week, gate, etc.)</label>
  <input name="availability_notes" placeholder="Looking for early arrival crew">

  <label>How should seekers contact you?</label>
  <input name="contact_method" placeholder="Post in comments, email us at...">

  <button type="submit">List Your Openings →</button>
</form>
{_DISCLAIMER_HTML}
</body></html>
"""

_INFRA_FORM_HTML = f"""
<!DOCTYPE html><html><head><title>Share Infra Signals – Rising Sparks</title>
<style>{_BASE_CSS}</style></head><body>
<div class="nav"><a href="/forms/">← Back</a></div>
<h1>We need or can offer infrastructure</h1>
<form method="post" action="/forms/infra">
  <label>Your name / handle *</label>
  <input name="display_name" required maxlength="80">

  <label>Is this a need or an offer? *</label>
  <select name="infra_role" required>
    <option value="seeking">We need something</option>
    <option value="offering">We can offer / lend / share</option>
  </select>

  <label>What categories fit best? (comma-separated) *</label>
  <input name="infra_categories" required placeholder="power, shade, tools, kitchen">
  <div class="hint">Use short tags like power, transport, water, tools, sound_gear.</div>

  <label>Quantity / size / amount</label>
  <input name="quantity" placeholder="e.g. 2 generators, 40ft shade cloth">

  <label>Condition</label>
  <select name="condition">
    <option value="">Unknown / not relevant</option>
    <option value="new">New</option>
    <option value="good">Good</option>
    <option value="fair">Fair</option>
    <option value="worn">Worn</option>
    <option value="needs_repair">Needs repair</option>
  </select>

  <label>When is it needed / available?</label>
  <input name="dates_needed" placeholder="e.g. build week, Aug 20-31, strike only">

  <label>Details</label>
  <textarea name="bio" rows="5" maxlength="2000"></textarea>
  <div class="hint">Describe the gear, constraints, pickup/dropoff, or anything moderators should know.</div>

  <label>How should people contact you?</label>
  <input name="contact_method" placeholder="DM on Reddit, email, etc.">

  <button type="submit">Share Infra Signal →</button>
</form>
{_DISCLAIMER_HTML}
</body></html>
"""

_THANKS_HTML = f"""
<!DOCTYPE html><html><head><title>Welcome to the Pool – Rising Sparks</title>
<style>{_BASE_CSS}</style></head><body>
<h1>Welcome to the pool.</h1>
<p>We’ve received your signals. Our volunteer moderators will review them to find potential connections.</p>
<p>If we find a likely match, we’ll reach out to make a human introduction.</p>
<div class="nav"><a href="/forms/">Submit another signal →</a></div>
{_DISCLAIMER_HTML}
</body></html>
"""


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


@router.get("/infra", response_class=HTMLResponse)
async def infra_form() -> str:
    return _INFRA_FORM_HTML


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
        platform_post_id=f"intake_seeker_{datetime.now(UTC).timestamp()}",
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
        platform_post_id=f"intake_camp_{datetime.now(UTC).timestamp()}",
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


@router.post("/infra")
async def infra_submit(
    display_name: Annotated[str, Form()],
    infra_role: Annotated[str, Form()],
    infra_categories: Annotated[str, Form()],
    quantity: Annotated[str, Form()] = "",
    condition: Annotated[str, Form()] = "",
    dates_needed: Annotated[str, Form()] = "",
    bio: Annotated[str, Form()] = "",
    contact_method: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(_get_session),
) -> RedirectResponse:
    title = f"[Intake] Infra {infra_role.title()}: {display_name}"
    body_parts = [f"Infra role: {infra_role}", f"Categories: {infra_categories}"]
    if quantity:
        body_parts.append(f"Quantity: {quantity}")
    if condition:
        body_parts.append(f"Condition: {condition}")
    if dates_needed:
        body_parts.append(f"Dates needed: {dates_needed}")
    if bio:
        body_parts.append(bio)
    if contact_method:
        body_parts.append(f"Contact: {contact_method}")

    post = Post(
        platform=Platform.MANUAL,
        platform_post_id=f"intake_infra_{datetime.now(UTC).timestamp()}",
        platform_author_id=display_name,
        author_display_name=display_name,
        source_url="",
        source_community="intake_form",
        title=title,
        raw_text="\n".join(body_parts),
        status=PostStatus.RAW,
        post_type=PostType.INFRASTRUCTURE,
        role=PostRole.UNKNOWN,
        infra_role=infra_role.strip().lower() or None,
        quantity=quantity or None,
        condition=condition or None,
        dates_needed=dates_needed or None,
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
        from sqlmodel.ext.asyncio.session import AsyncSession

        from matchbot.db.engine import get_engine
        from matchbot.extraction import process_post
        from matchbot.extraction.anthropic_extractor import AnthropicExtractor
        from matchbot.extraction.openai_extractor import OpenAIExtractor
        from matchbot.settings import get_settings

        settings = get_settings()
        extractor = (
            AnthropicExtractor()
            if settings.llm_provider == "anthropic"
            else OpenAIExtractor()
        )

        async with AsyncSession(get_engine(), expire_on_commit=False) as session:
            post = await session.get(Post, post_id)
            if post:
                try:
                    await process_post(session, post, extractor)
                finally:
                    await extractor.aclose()

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        pass  # No running loop — extraction will need to be triggered manually
