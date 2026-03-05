"""Public community showcase page and data endpoint."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.models import Match, MatchStatus, Post, PostStatus
from matchbot.settings import get_settings

router = APIRouter(prefix="/community", tags=["community"])


async def _get_session():
    from matchbot.db.engine import get_engine

    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        yield session


_COMMUNITY_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Matchbot Community Value</title>
  <style>
    :root {
      --sand: #f4e6cf;
      --dust: #e3cfa8;
      --ink: #222021;
      --ember: #c54b1b;
      --sun: #ffb74a;
      --sage: #2d5b4f;
      --paper: #fff9ef;
      --card: #fffdf8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Avenir Next", "Trebuchet MS", Verdana, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 20% 10%, rgba(255, 183, 74, 0.35), transparent 45%),
        radial-gradient(circle at 85% 25%, rgba(197, 75, 27, 0.24), transparent 40%),
        linear-gradient(170deg, var(--sand), var(--paper));
      min-height: 100vh;
    }
    .wrap { max-width: 1024px; margin: 0 auto; padding: 40px 18px 72px; }
    .hero {
      border: 1px solid rgba(34, 32, 33, 0.12);
      border-radius: 22px;
      background: rgba(255, 253, 248, 0.78);
      backdrop-filter: blur(2px);
      padding: 28px 22px;
      box-shadow: 0 10px 25px rgba(34, 32, 33, 0.08);
    }
    .eyebrow {
      font-size: 13px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--sage);
    }
    h1 { margin: 8px 0 10px; font-size: clamp(28px, 5vw, 48px); line-height: 1.05; }
    .sub { margin: 0; font-size: clamp(16px, 2.2vw, 20px); max-width: 54ch; color: #3f3c3d; }
    .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 18px; }
    .card {
      background: var(--card);
      border-radius: 16px;
      border: 1px solid rgba(34, 32, 33, 0.1);
      padding: 14px;
      box-shadow: 0 6px 14px rgba(34, 32, 33, 0.06);
    }
    .kicker { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: #6a6264; }
    .metric { font-size: clamp(24px, 3vw, 34px); margin: 5px 0; font-weight: 700; }
    .note { margin: 0; font-size: 13px; color: #6a6264; }
    .section-title { margin: 32px 0 10px; font-size: 23px; }
    .pipeline { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
    .pipe {
      background: rgba(255, 255, 255, 0.8);
      border: 1px solid rgba(34, 32, 33, 0.12);
      border-radius: 14px;
      padding: 12px;
      position: relative;
      overflow: hidden;
    }
    .pipe::after {
      content: "";
      position: absolute;
      inset: auto -20px -20px auto;
      width: 90px;
      height: 90px;
      background: radial-gradient(circle, rgba(255, 183, 74, 0.3), transparent 65%);
    }
    .stories { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
    .story-title { font-size: 18px; margin: 0 0 6px; }
    .story p { margin: 8px 0; font-size: 14px; line-height: 1.45; }
    .label { font-weight: 700; color: #3a3a3a; }
    .cta {
      margin-top: 26px;
      border-radius: 18px;
      background: linear-gradient(125deg, #2b4f44, #1f3932);
      color: #f8f7f5;
      padding: 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
    }
    .cta a {
      display: inline-block;
      text-decoration: none;
      background: var(--sun);
      color: #2a1706;
      font-weight: 700;
      border-radius: 999px;
      padding: 10px 18px;
    }
    .updated { margin-top: 10px; font-size: 12px; color: #6a6264; }
    .hidden { opacity: 0; transform: translateY(8px); animation: rise 420ms ease forwards; }
    @keyframes rise { to { opacity: 1; transform: translateY(0); } }
    @media (max-width: 880px) {
      .grid, .pipeline, .stories { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 620px) {
      .grid, .pipeline, .stories { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero hidden" style="animation-delay:60ms">
      <div class="eyebrow">Community Matchmaking, Human-Led</div>
      <h1>Show more good-fit connections. Miss fewer people.</h1>
      <p class="sub">
        Matchbot helps volunteers triage public posts, surface likely fits, and send
        moderator-reviewed introductions faster.
      </p>
      <div class="grid" id="summary-grid"></div>
    </section>

    <h2 class="section-title hidden" style="animation-delay:120ms">How the flow works</h2>
    <section class="pipeline hidden" style="animation-delay:160ms" id="pipeline"></section>

    <h2 class="section-title hidden" style="animation-delay:220ms">Recent anonymized examples</h2>
    <section class="stories hidden" style="animation-delay:260ms" id="stories"></section>

    <section class="cta hidden" style="animation-delay:320ms">
      <div>
        <strong>How would you improve this?</strong><br>
        Tell us what feels useful, missing, or too complicated.
      </div>
      <a id="feedback-link" href="/forms/">Send Organizer Feedback</a>
    </section>
    <div class="updated" id="updated"></div>
  </main>
  <script>
    const fmt = (n) => new Intl.NumberFormat().format(n || 0);

    function metricCard(label, value, note) {
      return `
        <article class="card">
          <div class="kicker">${label}</div>
          <div class="metric">${fmt(value)}</div>
          <p class="note">${note}</p>
        </article>
      `;
    }

    function pipelineCard(stage, count) {
      return `
        <article class="pipe">
          <div class="kicker">${stage}</div>
          <div class="metric">${fmt(count)}</div>
        </article>
      `;
    }

    function storyCard(story) {
      return `
        <article class="card story">
          <h3 class="story-title">${story.title}</h3>
          <p><span class="label">Need:</span> ${story.problem}</p>
          <p><span class="label">Action:</span> ${story.intervention}</p>
          <p><span class="label">Signal:</span> ${story.outcome}</p>
          <p class="note">${story.confidence_note}</p>
        </article>
      `;
    }

    async function load() {
      const res = await fetch("/community/data");
      const data = await res.json();

      const summary = data.summary || {};
      const weekly = data.weekly || {};
      const backlog = data.backlog || {};

      document.getElementById("summary-grid").innerHTML = [
        metricCard(
          "Posts Ingested",
          summary.total_ingested,
          `${fmt(weekly.ingested_7d)} in last 7 days`
        ),
        metricCard(
          "Structured Posts",
          summary.indexed,
          `${fmt(weekly.indexed_7d)} indexed in last 7 days`
        ),
        metricCard(
          "Potential Matches",
          summary.proposed_matches,
          `${fmt(weekly.matches_7d)} new in last 7 days`
        ),
        metricCard(
          "Introductions Sent",
          summary.intros_sent,
          `${fmt(weekly.intros_7d)} in last 7 days`
        ),
      ].join("");

      document.getElementById("pipeline").innerHTML =
        (data.pipeline || []).map((x) => pipelineCard(x.stage, x.count)).join("");

      const stories = data.stories || [];
      document.getElementById("stories").innerHTML = stories.length
        ? stories.map(storyCard).join("")
        : (
          `<article class="card"><p class="note">` +
          `No examples yet. As activity grows, anonymized stories appear here.` +
          `</p></article>`
        );

      if (data.cta && data.cta.feedback_url) {
        document.getElementById("feedback-link").href = data.cta.feedback_url;
      }

      const backlogText = backlog.oldest_needs_review_age_hours == null
        ? "No review backlog right now."
        : `Oldest pending review: ${backlog.oldest_needs_review_age_hours}h`;
      document.getElementById("updated").textContent = (
        `Needs review: ${fmt(backlog.needs_review_count)} • ` +
        `${backlogText} • Updated ${new Date(data.updated_at).toLocaleString()}`
      );
    }

    load();
  </script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
async def community_page() -> str:
    return _COMMUNITY_HTML


@router.get("/data")
async def community_data(session: AsyncSession = Depends(_get_session)) -> dict[str, Any]:
    return await build_public_community_payload(session)


async def build_public_community_payload(session: AsyncSession) -> dict[str, Any]:
    now = datetime.now(UTC)
    now_naive = now.replace(tzinfo=None)
    seven_days_ago = now_naive - timedelta(days=7)

    posts = (await session.exec(select(Post))).all()
    matches = (await session.exec(select(Match))).all()

    intro_terminal = {
        MatchStatus.INTRO_SENT,
        MatchStatus.CONVERSATION_STARTED,
        MatchStatus.ACCEPTED_PENDING,
        MatchStatus.ONBOARDED,
    }

    total_ingested = len(posts)
    indexed_count = sum(1 for p in posts if p.status == PostStatus.INDEXED)
    proposed_matches = len(matches)
    intros_sent = sum(1 for m in matches if m.status in intro_terminal)

    ingested_7d = sum(1 for p in posts if p.detected_at >= seven_days_ago)
    indexed_7d = sum(
        1 for p in posts if p.status == PostStatus.INDEXED and p.detected_at >= seven_days_ago
    )
    matches_7d = sum(1 for m in matches if m.created_at >= seven_days_ago)
    intros_7d = sum(
        1 for m in matches if m.intro_sent_at is not None and m.intro_sent_at >= seven_days_ago
    )

    needs_review_posts = [p for p in posts if p.status == PostStatus.NEEDS_REVIEW]
    oldest_needs_review_age_hours: float | None = None
    if needs_review_posts:
        oldest = min(needs_review_posts, key=lambda p: p.detected_at)
        oldest_needs_review_age_hours = round(
            (now_naive - oldest.detected_at).total_seconds() / 3600, 1
        )

    platform_counts = Counter(p.platform for p in posts)
    platform_mix = []
    for platform, count in sorted(platform_counts.items(), key=lambda x: x[1], reverse=True):
        pct = round((count / total_ingested) * 100, 1) if total_ingested else 0.0
        platform_mix.append({"platform": platform, "count": count, "pct": pct})

    structured_count = sum(1 for p in posts if p.status != PostStatus.RAW)
    pipeline = [
        {"stage": "Ingested", "count": total_ingested},
        {"stage": "Structured", "count": structured_count},
        {"stage": "Potential Matches", "count": proposed_matches},
        {"stage": "Intros Sent", "count": intros_sent},
    ]

    stories = _build_stories(posts, matches)
    settings = get_settings()

    feedback_url = "/forms/"
    if settings.community_feedback_email:
        feedback_url = (
            f"mailto:{settings.community_feedback_email}"
            "?subject=Matchbot%20Community%20Feedback"
            "&body=How%20would%20you%20improve%20it%3F"
        )
    elif settings.community_feedback_url:
        feedback_url = settings.community_feedback_url

    return {
        "summary": {
            "total_ingested": total_ingested,
            "indexed": indexed_count,
            "proposed_matches": proposed_matches,
            "intros_sent": intros_sent,
        },
        "weekly": {
            "ingested_7d": ingested_7d,
            "indexed_7d": indexed_7d,
            "matches_7d": matches_7d,
            "intros_7d": intros_7d,
        },
        "backlog": {
            "needs_review_count": len(needs_review_posts),
            "oldest_needs_review_age_hours": oldest_needs_review_age_hours,
        },
        "platform_mix": platform_mix,
        "pipeline": pipeline,
        "stories": stories,
        "cta": {"feedback_url": feedback_url},
        "updated_at": now.isoformat(),
    }


def _build_stories(posts: list[Post], matches: list[Match]) -> list[dict[str, str]]:
    post_by_id = {p.id: p for p in posts}
    story_rows: list[dict[str, str]] = []
    sorted_matches = sorted(matches, key=lambda m: m.created_at, reverse=True)

    for idx, match in enumerate(sorted_matches, start=1):
        seeker = post_by_id.get(match.seeker_post_id)
        camp = post_by_id.get(match.camp_post_id)
        if seeker is None or camp is None:
            continue

        overlap = sorted(
            set(seeker.contribution_types_list()).intersection(camp.contribution_types_list())
        )
        overlap_text = ", ".join(overlap[:3]) if overlap else "shared contribution signals"
        story_rows.append(
            {
                "title": f"Connection Opportunity {idx}",
                "problem": _sanitize_text(seeker.raw_text or seeker.title, max_len=140),
                "intervention": f"Matched with a compatible camp using {overlap_text}.",
                "outcome": _outcome_label(match.status),
                "confidence_note": _confidence_note(match),
            }
        )
        if len(story_rows) >= 3:
            break

    if story_rows:
        return story_rows

    indexed_posts = [p for p in posts if p.status == PostStatus.INDEXED]
    for idx, post in enumerate(
        sorted(indexed_posts, key=lambda p: p.detected_at, reverse=True),
        start=1,
    ):
        story_rows.append(
            {
                "title": f"Active Request {idx}",
                "problem": _sanitize_text(post.raw_text or post.title, max_len=140),
                "intervention": "Post was structured and added to the matching pool.",
                "outcome": "Awaiting the best-fit counterpart.",
                "confidence_note": "Anonymized community example.",
            }
        )
        if len(story_rows) >= 3:
            break

    return story_rows


def _outcome_label(status: str) -> str:
    if status == MatchStatus.INTRO_SENT:
        return "Moderator intro sent."
    if status == MatchStatus.CONVERSATION_STARTED:
        return "Conversation started."
    if status in {MatchStatus.ACCEPTED_PENDING, MatchStatus.ONBOARDED}:
        return "Connection progressed beyond intro."
    if status == MatchStatus.APPROVED:
        return "Approved for introduction."
    return "Queued for moderator review."


def _confidence_note(match: Match) -> str:
    if match.confidence is not None:
        return f"Confidence signal: {round(match.confidence * 100)}%."
    if match.score:
        return f"Compatibility score: {round(match.score * 100)}%."
    return "Scored using structured fit signals."


def _sanitize_text(text: str, *, max_len: int = 160) -> str:
    compact = " ".join((text or "").split())
    compact = re.sub(r"https?://\S+", "[link]", compact)
    compact = re.sub(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b", "[contact]", compact)
    compact = re.sub(r"\bu/[A-Za-z0-9_-]+\b", "u/[redacted]", compact)
    compact = re.sub(r"@[A-Za-z0-9_]{2,}", "@[redacted]", compact)
    compact = re.sub(r"\bt2_[A-Za-z0-9_]+\b", "[user]", compact)
    if len(compact) > max_len:
        return compact[: max_len - 1].rstrip() + "…"
    return compact
