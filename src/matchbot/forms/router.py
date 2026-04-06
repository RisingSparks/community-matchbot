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
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.branding import (
    BRAND_FONT_STYLESHEET,
    FAVICON_LINK_TAGS,
    build_brand_logo_link,
    build_google_analytics_tags,
    build_meta_tags,
)
from matchbot.db.models import Platform, Post, PostRole, PostStatus, PostType


async def _get_session():
    """FastAPI-compatible async session dependency."""
    from matchbot.db.engine import get_engine
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        yield session

router = APIRouter(prefix="/forms", tags=["intake"])


def _clean_http_url(url: str) -> str:
    """Keep only http(s) URLs from form submissions."""
    candidate = (url or "").strip()
    if not candidate:
        return ""
    parsed = urlparse(candidate)
    return candidate if parsed.scheme in ("http", "https") else ""

# ---------------------------------------------------------------------------
# Minimal inline HTML — avoids external template file dependency
# ---------------------------------------------------------------------------

_BASE_CSS = """
@import url('""" + BRAND_FONT_STYLESHEET + """');

:root {
  --bg: #f7f3e9;
  --surface: rgba(255, 255, 255, 0.9);
  --surface-hover: #ffffff;
  --border: rgba(0, 0, 0, 0.14);
  --border-light: rgba(74, 74, 74, 0.18);
  --spark: #ff9200;
  --spark-deep: #d97700;
  --text: #000000;
  --text-muted: #4a4a4a;
  --text-dim: #6d655a;
  --radius: 18px;
  --max-w: 760px;
  --shadow: 0 18px 44px rgba(0, 0, 0, 0.08);
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 16px; scroll-behavior: smooth; }

body {
  background-color: var(--bg);
  background-image:
    radial-gradient(circle at 12% 0%, rgba(255, 146, 0, 0.2), transparent 28%),
    radial-gradient(circle at 88% 18%, rgba(0, 0, 0, 0.05), transparent 24%),
    linear-gradient(180deg, #fbf8f0 0%, var(--bg) 100%);
  color: var(--text);
  font-family: 'Merriweather', Georgia, serif;
  line-height: 1.7;
  min-height: 100vh;
  padding: 0 20px 80px;
}

body::before {
  content: "";
  position: fixed;
  top: -50%; left: -50%;
  width: 200%; height: 200%;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.7' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='300' height='300' filter='url(%23n)'/%3E%3C/svg%3E");
  opacity: 0.018;
  pointer-events: none;
  z-index: 9999;
}

.page {
  max-width: var(--max-w);
  margin: 0 auto;
  padding-top: 44px;
}

.site-header {
  margin-bottom: 38px;
}
.brand-lockup {
  display: inline-flex;
  align-items: center;
  gap: 14px;
  text-decoration: none;
  color: var(--text);
}
.brand-lockup__image {
  width: 62px;
  height: auto;
  display: block;
}
.brand-lockup__text {
  font-family: 'Oswald', 'Anton', Impact, sans-serif;
  font-size: 1.55rem;
  line-height: 1;
  letter-spacing: 0.01em;
}

.back-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-family: 'Oswald', 'Anton', Impact, sans-serif;
  font-size: 0.95rem;
  letter-spacing: 0.02em;
  color: var(--text-muted);
  text-decoration: none;
  margin-bottom: 36px;
  transition: color 0.2s;
}
.back-link:hover { color: var(--spark-deep); }

h1 {
  font-family: 'Anton', Impact, sans-serif;
  font-size: clamp(2.5rem, 6vw, 4.4rem);
  font-weight: 400;
  line-height: 0.98;
  letter-spacing: 0.01em;
  color: var(--text);
  margin-bottom: 14px;
}
h1 em { font-style: normal; color: var(--spark); }

.lede {
  font-size: 1rem;
  color: var(--text-muted);
  line-height: 1.9;
  margin-bottom: 44px;
  max-width: 52ch;
}

.choices {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-bottom: 56px;
}
.choice-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 24px 28px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  text-decoration: none;
  color: var(--text);
  transition: background 0.18s, border-color 0.18s, transform 0.15s, box-shadow 0.18s;
  box-shadow: var(--shadow);
}
.choice-card:hover {
  background: var(--surface-hover);
  border-color: rgba(255, 146, 0, 0.45);
  transform: translateY(-2px);
  box-shadow: 0 20px 48px rgba(0, 0, 0, 0.12);
}
.choice-body { flex: 1; }
.choice-label {
  font-family: 'Oswald', 'Anton', Impact, sans-serif;
  font-size: 1.4rem;
  font-weight: 500;
  letter-spacing: 0.01em;
  display: block;
  line-height: 1.05;
}
.choice-sub {
  font-size: 0.9rem;
  color: var(--text-muted);
  margin-top: 8px;
  line-height: 1.55;
  display: block;
}
.choice-arrow {
  color: var(--spark);
  font-size: 1.55rem;
  flex-shrink: 0;
  transition: transform 0.18s;
}
.choice-card:hover .choice-arrow { transform: translateX(4px); }

.form-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 36px 40px;
  margin-bottom: 44px;
  box-shadow: var(--shadow);
}
.form-section-label {
  font-family: 'Oswald', 'Anton', Impact, sans-serif;
  font-size: 0.88rem;
  font-weight: 500;
  letter-spacing: 0.06em;
  color: var(--spark);
  margin-bottom: 28px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-light);
}
.field { margin-bottom: 22px; }
.field:last-of-type { margin-bottom: 0; }

label {
  display: block;
  font-size: 0.875rem;
  color: var(--text-muted);
  margin-bottom: 7px;
  letter-spacing: 0.015em;
}
label .req { color: var(--spark); margin-left: 2px; }

input[type=text], input[type=number], input[type=email],
textarea, select {
  width: 100%;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid var(--border);
  border-radius: 12px;
  color: var(--text);
  font-family: 'Merriweather', Georgia, serif;
  font-size: 0.9rem;
  line-height: 1.5;
  transition: border-color 0.2s, box-shadow 0.2s;
  -webkit-appearance: none;
  appearance: none;
}
input::placeholder, textarea::placeholder { color: var(--text-dim); }
input:focus, textarea:focus, select:focus {
  outline: none;
  border-color: rgba(255, 146, 0, 0.7);
  box-shadow: 0 0 0 4px rgba(255, 146, 0, 0.14);
}
textarea { resize: vertical; min-height: 108px; }
select {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath fill='%234a4a4a' d='M6 8L0 0h12z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 14px center;
  padding-right: 38px;
}
.hint {
  font-size: 0.78rem;
  color: var(--text-dim);
  margin-top: 5px;
  line-height: 1.5;
}
.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.btn-submit {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-top: 28px;
  padding: 14px 28px;
  background: var(--spark);
  color: #000;
  font-family: 'Oswald', 'Anton', Impact, sans-serif;
  font-size: 0.9rem;
  font-weight: 500;
  letter-spacing: 0.03em;
  border: none;
  border-radius: 999px;
  cursor: pointer;
  transition: background 0.18s, transform 0.15s, box-shadow 0.18s;
  box-shadow: 0 10px 26px rgba(255, 146, 0, 0.24);
}
.btn-submit:hover {
  background: #ff9e19;
  transform: translateY(-1px);
  box-shadow: 0 14px 30px rgba(255, 146, 0, 0.32);
}
.btn-submit:active { transform: translateY(0); }

.disclaimer {
  font-size: 0.78rem;
  color: var(--text-dim);
  line-height: 1.65;
  padding-top: 28px;
  border-top: 1px solid var(--border-light);
}

.thanks-wrap {
  text-align: center;
  padding: 64px 20px;
}
.thanks-mark {
  width: 68px; height: 68px;
  background: var(--surface);
  border: 1px solid rgba(255, 146, 0, 0.38);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.6rem;
  margin: 0 auto 36px;
}
.thanks-wrap p {
  color: var(--text-muted);
  max-width: 380px;
  margin: 0 auto 12px;
  font-size: 0.95rem;
}
.return-link {
  display: inline-block;
  margin-top: 36px;
  color: var(--spark-deep);
  text-decoration: none;
  font-family: 'Oswald', 'Anton', Impact, sans-serif;
  font-size: 0.875rem;
  letter-spacing: 0.04em;
}
.return-link:hover { text-decoration: underline; }

.steps-heading {
  font-family: 'Anton', Impact, sans-serif;
  font-size: 0.82rem;
  font-weight: 400;
  letter-spacing: 0.06em;
  color: var(--text-dim);
  margin-bottom: 12px;
}
.steps {
  border-top: 1px solid var(--border-light);
  margin-bottom: 44px;
}
.step {
  display: flex;
  gap: 20px;
  padding: 16px 0;
  border-bottom: 1px solid var(--border-light);
}
.step-num {
  font-family: 'Anton', Impact, sans-serif;
  font-size: 1.35rem;
  color: var(--spark);
  font-weight: 400;
  min-width: 22px;
  line-height: 1.4;
  flex-shrink: 0;
}
.step-body { flex: 1; }
.step-title {
  display: block;
  font-size: 0.9rem;
  color: var(--text);
  margin-bottom: 1px;
  line-height: 1.4;
}
.step-desc {
  font-size: 0.8rem;
  color: var(--text-muted);
  line-height: 1.5;
}

/* Process note near submit */
.process-note {
  margin-top: 16px;
  font-size: 0.78rem;
  color: var(--text-dim);
  line-height: 1.55;
  max-width: 420px;
}

/* Fade-up entrance */
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(14px); }
  to   { opacity: 1; transform: translateY(0); }
}
.page > * {
  animation: fadeUp 0.45s ease backwards;
}
.page > *:nth-child(1) { animation-delay: 0.04s; }
.page > *:nth-child(2) { animation-delay: 0.1s; }
.page > *:nth-child(3) { animation-delay: 0.16s; }
.page > *:nth-child(4) { animation-delay: 0.22s; }
.page > *:nth-child(5) { animation-delay: 0.28s; }

@media (max-width: 520px) {
  .form-card { padding: 24px 20px; }
  .field-row { grid-template-columns: 1fr; }
  h1 { font-size: 2rem; }
  .brand-lockup__image { width: 52px; }
  .brand-lockup__text { font-size: 1.3rem; }
}
"""

_HEADER_HTML = (
    '<header class="site-header">'
    + build_brand_logo_link(
        "/forms/",
        link_class="brand-lockup",
        image_class="brand-lockup__image",
        text_class="brand-lockup__text",
    )
    + "</header>"
)

_DISCLAIMER_HTML = """
<div class="disclaimer">
  Rising Sparks is a grassroots collective, community-built, community-led. While we collaborate with folks across
  the ecosystem, this is 
</div>
"""


def _with_meta(
    html: str,
    *,
    existing_title: str,
    title: str,
    description: str,
    path: str,
    base_url: str,
    robots: str = "index,follow",
) -> str:
    meta_tags = build_meta_tags(
        title=title,
        description=description,
        path=path,
        base_url=base_url,
        robots=robots,
    )
    analytics_tags = build_google_analytics_tags()
    html = html.replace(f"<title>{existing_title}</title>", meta_tags, 1)
    if analytics_tags:
        html = html.replace("</head>", f"  {analytics_tags}\n</head>", 1)
    return html

_LANDING_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MatchBot by Rising Sparks — Find Your Community</title>
  {FAVICON_LINK_TAGS}
  <style>{_BASE_CSS}</style>
</head>
<body>
<div class="page">
  {_HEADER_HTML}

  <h1>Find your <em>community.</em><br>Build the city.</h1>
  <p class="lede">
    Matchbot connects self-motivated people with the camps and art projects
    where they can contribute, learn, and make something real.
    Fill out a short form and we will look for aligned connections.
  </p>

  <div class="choices">
    <a class="choice-card" href="/forms/seeker">
      <div class="choice-body">
        <span class="choice-label">I&#8217;m looking for a camp or art project</span>
        <span class="choice-sub">Find an aligned community where you can contribute, build, or learn</span>
      </div>
      <span class="choice-arrow">&#8594;</span>
    </a>
    <a class="choice-card" href="/forms/camp">
      <div class="choice-body">
        <span class="choice-label">We have openings for contributors</span>
        <span class="choice-sub">A camp or art project looking for motivated builders and crew</span>
      </div>
      <span class="choice-arrow">&#8594;</span>
    </a>
    <a class="choice-card" href="/forms/infra">
      <div class="choice-body">
        <span class="choice-label">I need gear — or have gear to offer</span>
        <span class="choice-sub">Shade, power, tools, transport, kitchen — seeking or lending</span>
      </div>
      <span class="choice-arrow">&#8594;</span>
    </a>
  </div>

  __OPT_OUT_NOTE__
  {_DISCLAIMER_HTML}
</div>
</body>
</html>
"""

_SEEKER_FORM_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Find Your Community — Rising Sparks</title>
  {FAVICON_LINK_TAGS}
  <style>{_BASE_CSS}</style>
</head>
<body>
<div class="page">
  {_HEADER_HTML}

  <a class="back-link" href="/forms/">&#8592; Back</a>
  <h1>Find a Camp or<br><em>Art Project</em></h1>
  <p class="lede">
    Tell us who you are, what you can contribute, and what you&#8217;re looking for.
    We review submissions manually and reach out if we find a good fit.
  </p>

  <form method="post" action="/forms/seeker">
    <div class="form-card">
      <div class="form-section-label">About you</div>

      <div class="field">
        <label>How should we call you?<span class="req">*</span></label>
        <input type="text" name="display_name" required maxlength="80" placeholder="Name or handle">
      </div>

      <div class="field">
        <label>What are you building?</label>
        <textarea name="bio" maxlength="2000" placeholder="Tell us about your skills, your experience, and what draws you to the dust&#8230;"></textarea>
        <div class="hint">This helps us understand your contribution style. Be as specific or as open as you like.</div>
      </div>

      <div class="field">
        <label>Vibes you&#8217;re looking for</label>
        <input type="text" name="vibes" placeholder="art, build_focused, sober, late-night, wellness&#8230;">
        <div class="hint">Comma-separated tags. e.g. loud, family_friendly, workshop, party</div>
      </div>

      <div class="field">
        <label>What can you contribute?</label>
        <input type="text" name="contributions" placeholder="build, art, kitchen, medic, sound&#8230;">
        <div class="hint">Comma-separated roles or skills you&#8217;re offering or eager to learn.</div>
      </div>
    </div>

    <div class="form-card">
      <div class="form-section-label">Logistics</div>

      <div class="field-row">
        <div class="field">
          <label>Year</label>
          <input type="number" name="year" min="2020" max="2040" placeholder="2026">
        </div>
        <div class="field">
          <label>How to reach you</label>
          <input type="text" name="contact_method" placeholder="Reddit DM, email&#8230;">
        </div>
      </div>

      <div class="field">
        <label>Availability &amp; dates</label>
        <input type="text" name="availability_notes" placeholder="e.g. Available for build week and the full event">
      </div>
    </div>

    <button class="btn-submit" type="submit">Join the pool &#8594;</button>
    <p class="process-note">
      We review submissions manually.
      If we find a good match, we&#8217;ll reach out to make a direct introduction — no automated spam.
    </p>
  </form>

  {_DISCLAIMER_HTML}
</div>
</body>
</html>
"""

_CAMP_FORM_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Find Your Builders — Rising Sparks</title>
  {FAVICON_LINK_TAGS}
  <style>{_BASE_CSS}</style>
</head>
<body>
<div class="page">
  {_HEADER_HTML}

  <a class="back-link" href="/forms/">&#8592; Back</a>
  <h1>Find Builders and<br><em>Collaborators</em></h1>
  <p class="lede">
    Tell us about your camp or art project and what you need.
    We look for motivated, aligned contributors and make introductions.
  </p>

  <form method="post" action="/forms/camp">
    <div class="form-card">
      <div class="form-section-label">Your project</div>

      <div class="field">
        <label>Camp or art project name<span class="req">*</span></label>
        <input type="text" name="camp_name" required maxlength="120" placeholder="Camp or project name">
      </div>

      <div class="field">
        <label>Your name or handle (project contact)<span class="req">*</span></label>
        <input type="text" name="display_name" required maxlength="80" placeholder="Who should we talk to?">
      </div>

      <div class="field">
        <label>Project URL</label>
        <input type="url" name="source_url" maxlength="500" placeholder="https://yourcamp.org or your listing URL">
        <div class="hint">Optional, but helpful. Add your website, directory listing, or original post link here instead of burying it in the description.</div>
      </div>

      <div class="field">
        <label>Tell us about your project</label>
        <textarea name="bio" maxlength="2000" placeholder="Describe your vibe, what you build, and what you expect from collaborators&#8230;"></textarea>
        <div class="hint">This is how motivated seekers will understand your world. Be honest about expectations, norms, and contribution style.</div>
      </div>

      <div class="field">
        <label>Project vibes</label>
        <input type="text" name="vibes" placeholder="art, build_focused, dance, sober&#8230;">
        <div class="hint">Comma-separated tags that describe your community&#8217;s culture and energy.</div>
      </div>

      <div class="field">
        <label>Who are you looking for?</label>
        <input type="text" name="contributions" placeholder="build, art, kitchen, sound, logistics&#8230;">
        <div class="hint">Roles, skills, or types of contribution you need — or are open to mentoring.</div>
      </div>
    </div>

    <div class="form-card">
      <div class="form-section-label">Logistics</div>

      <div class="field-row">
        <div class="field">
          <label>Year</label>
          <input type="number" name="year" min="2020" max="2040" placeholder="2026">
        </div>
        <div class="field">
          <label>Approximate group size</label>
          <input type="number" name="camp_size" min="1" max="5000" placeholder="50">
        </div>
      </div>

      <div class="field">
        <label>Availability &amp; timing</label>
        <input type="text" name="availability_notes" placeholder="e.g. Looking for early arrival crew, build week, full event">
      </div>

      <div class="field">
        <label>How should seekers contact you?</label>
        <input type="text" name="contact_method" placeholder="Comments, email, DM&#8230;">
      </div>
    </div>

    <button class="btn-submit" type="submit">List your openings &#8594;</button>
    <p class="process-note">
      We review submissions manually.
      If we find a good match, we&#8217;ll reach out to both parties with a direct introduction.
    </p>
  </form>

  {_DISCLAIMER_HTML}
</div>
</body>
</html>
"""

_INFRA_FORM_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Share an Infra Signal — Rising Sparks</title>
  {FAVICON_LINK_TAGS}
  <style>{_BASE_CSS}</style>
</head>
<body>
<div class="page">
  {_HEADER_HTML}

  <a class="back-link" href="/forms/">&#8592; Back</a>
  <h1>We need — or can offer —<br><em>infrastructure</em></h1>
  <p class="lede">
    Gear, tools, shade, power, water, transport.
    Share what you need or what you can lend, and we&#8217;ll find the match.
  </p>

  <form method="post" action="/forms/infra">
    <div class="form-card">
      <div class="form-section-label">Your signal</div>

      <div class="field">
        <label>Your name or handle<span class="req">*</span></label>
        <input type="text" name="display_name" required maxlength="80" placeholder="Name or handle">
      </div>

      <div class="field">
        <label>Is this a need or an offer?<span class="req">*</span></label>
        <select name="infra_role" required>
          <option value="seeking">We need something</option>
          <option value="offering">We can offer / lend / share</option>
        </select>
      </div>

      <div class="field">
        <label>Categories<span class="req">*</span></label>
        <input type="text" name="infra_categories" required placeholder="power, shade, tools, kitchen&#8230;">
        <div class="hint">Comma-separated tags: power, transport, water, tools, shade, sound_gear, kitchen&#8230;</div>
      </div>

      <div class="field-row">
        <div class="field">
          <label>Quantity / size</label>
          <input type="text" name="quantity" placeholder="e.g. 2 generators, 40ft shade cloth">
        </div>
        <div class="field">
          <label>Condition</label>
          <select name="condition">
            <option value="">Unknown / not relevant</option>
            <option value="new">New</option>
            <option value="good">Good</option>
            <option value="fair">Fair</option>
            <option value="worn">Worn</option>
            <option value="needs_repair">Needs repair</option>
          </select>
        </div>
      </div>

      <div class="field">
        <label>When is it needed or available?</label>
        <input type="text" name="dates_needed" placeholder="e.g. build week, Aug 20&#8211;31, strike only">
      </div>

      <div class="field">
        <label>Details</label>
        <textarea name="bio" maxlength="2000" placeholder="Describe the gear, constraints, pickup/dropoff, or anything we should know&#8230;"></textarea>
      </div>

      <div class="field">
        <label>How should people contact you?</label>
        <input type="text" name="contact_method" placeholder="Reddit DM, email&#8230;">
      </div>
    </div>

    <button class="btn-submit" type="submit">Share infra signal &#8594;</button>
  </form>

  {_DISCLAIMER_HTML}
</div>
</body>
</html>
"""

_THANKS_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Welcome to the Pool — Rising Sparks</title>
  {FAVICON_LINK_TAGS}
  <style>{_BASE_CSS}</style>
</head>
<body>
<div class="page">
  {_HEADER_HTML}

  <div class="thanks-wrap">
    <div class="thanks-mark">&#10024;</div>
    <h1>Welcome to<br>the <em>pool.</em></h1>
    <p>We&#8217;ve received your signal.</p>
    <p>
      We&#8217;ll review it and look for aligned connections.
      If we find a likely match, we&#8217;ll reach out to make a human introduction.
    </p>
    <a class="return-link" href="/forms/">Submit another signal &#8594;</a>
    __OPT_OUT_NOTE__
  </div>

  {_DISCLAIMER_HTML}
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def intake_landing(request: Request) -> str:
    from matchbot.settings import get_settings

    settings = get_settings()
    support_email = settings.community_feedback_email
    if support_email:
        opt_out_note = (
            f'<p style="font-size:0.85rem;color:#888;text-align:center;margin-top:1.5rem;">'
            f'Don&#8217;t want your post here? <a href="mailto:{support_email}" style="color:#c84b31;">Email us</a> to opt out.</p>'
        )
    else:
        opt_out_note = ""
    landing_html = _LANDING_HTML.replace("__OPT_OUT_NOTE__", opt_out_note)
    return _with_meta(
        landing_html,
        existing_title="MatchBot by Rising Sparks — Find Your Community",
        title="Rising Sparks | Community Finder for Camps, Art Projects, and Infra",
        description=(
            "MatchBot is a community discovery tool that helps self-motivated "
            "Burners find aligned camps, art projects, and infrastructure opportunities."
        ),
        path="/forms/",
        base_url=str(request.base_url),
    )


@router.get("/seeker", response_class=HTMLResponse)
async def seeker_form(request: Request) -> str:
    return _with_meta(
        _SEEKER_FORM_HTML,
        existing_title="Find Your Community — Rising Sparks",
        title="Find a Camp or Art Project | Rising Sparks",
        description=(
            "Share your skills, interests, and availability to find aligned camps or art "
            "projects through MatchBot's human-reviewed discovery flow."
        ),
        path="/forms/seeker",
        base_url=str(request.base_url),
    )


@router.get("/camp", response_class=HTMLResponse)
async def camp_form(request: Request) -> str:
    return _with_meta(
        _CAMP_FORM_HTML,
        existing_title="Find Your Builders — Rising Sparks",
        title="Find Builders and Collaborators | Rising Sparks",
        description=(
            "Tell MatchBot about your camp or art project to surface aligned builders, "
            "crew, and collaborators through thoughtful introductions."
        ),
        path="/forms/camp",
        base_url=str(request.base_url),
    )


@router.get("/infra", response_class=HTMLResponse)
async def infra_form(request: Request) -> str:
    return _with_meta(
        _INFRA_FORM_HTML,
        existing_title="Share an Infra Signal — Rising Sparks",
        title="Share Infrastructure Needs or Offers | Rising Sparks",
        description=(
            "Post infrastructure needs or offers for shade, power, transport, tools, kitchen, "
            "and other camp logistics through MatchBot."
        ),
        path="/forms/infra",
        base_url=str(request.base_url),
    )


@router.get("/thanks", response_class=HTMLResponse)
async def intake_thanks(request: Request) -> str:
    from matchbot.settings import get_settings

    settings = get_settings()
    support_email = settings.community_feedback_email
    if support_email:
        opt_out_note = (
            f'<p style="margin-top:1.5rem;font-size:0.85rem;color:#888;">'
            f'Changed your mind? <a href="mailto:{support_email}" style="color:#c84b31;">Email us</a>'
            f" to remove your listing.</p>"
        )
    else:
        opt_out_note = ""
    thanks_html = _THANKS_HTML.replace("__OPT_OUT_NOTE__", opt_out_note)
    return _with_meta(
        thanks_html,
        existing_title="Welcome to the Pool — Rising Sparks",
        title="Submission Received | Rising Sparks",
        description=(
            "MatchBot received your signal. We will review it and follow "
            "up if we find an aligned connection."
        ),
        path="/forms/thanks",
        base_url=str(request.base_url),
        robots="noindex,nofollow",
    )


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
    source_url: Annotated[str, Form()] = "",
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
    cleaned_source_url = _clean_http_url(source_url)
    if cleaned_source_url:
        body_parts.append(f"URL: {cleaned_source_url}")
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
        source_url=cleaned_source_url,
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
