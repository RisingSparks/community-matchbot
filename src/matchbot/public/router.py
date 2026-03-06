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

from matchbot.db.models import Match, MatchStatus, Post, PostRole, PostStatus, Profile
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
  <title>Rising Sparks Community Dashboard</title>
  <style>
    :root {
      --sand: #f4e6cf;
      --dust: #e3cfa8;
      --ink: #222021;
      --sun: #ffb74a;
      --sage: #2d5b4f;
      --paper: #fff9ef;
      --card: #fffdf8;
      --muted: #6a6264;
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
    .wrap { max-width: 1120px; margin: 0 auto; padding: 36px 18px 72px; }
    .hero, .panel {
      border: 1px solid rgba(34, 32, 33, 0.12);
      border-radius: 20px;
      background: rgba(255, 253, 248, 0.82);
      padding: 22px;
      box-shadow: 0 10px 25px rgba(34, 32, 33, 0.08);
      margin-bottom: 14px;
    }
    .eyebrow {
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--sage);
    }
    h1 { margin: 8px 0 10px; font-size: clamp(28px, 5vw, 46px); line-height: 1.05; }
    .sub { margin: 0; font-size: clamp(16px, 2.2vw, 20px); max-width: 54ch; color: #3f3c3d; }
    .section-title { margin: 8px 0 12px; font-size: 22px; }
    .grid4, .grid2, .grid3 { display: grid; gap: 10px; }
    .grid4 { grid-template-columns: repeat(4, 1fr); }
    .grid2 { grid-template-columns: repeat(2, 1fr); }
    .grid3 { grid-template-columns: repeat(3, 1fr); }
    .card {
      background: var(--card);
      border-radius: 14px;
      border: 1px solid rgba(34, 32, 33, 0.1);
      padding: 12px;
      box-shadow: 0 6px 14px rgba(34, 32, 33, 0.06);
    }
    .kicker {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }
    .metric { font-size: clamp(22px, 3vw, 32px); margin: 4px 0; font-weight: 700; }
    .note { margin: 0; font-size: 13px; color: var(--muted); }
    .pill {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.03em;
      background: #ece7dc;
      margin-bottom: 6px;
    }
    .timeline { max-height: 420px; overflow: auto; padding-right: 4px; }
    .event-row { border-bottom: 1px dashed rgba(34, 32, 33, 0.12); padding: 9px 0; }
    .event-row:last-child { border-bottom: none; }
    .event-meta { font-size: 12px; color: var(--muted); }
    .event-text { font-size: 14px; line-height: 1.4; margin-top: 2px; }
    .bars { display: flex; flex-direction: column; gap: 10px; }
    .bar-row {
      display: grid;
      grid-template-columns: 120px 1fr 42px;
      gap: 10px;
      align-items: center;
    }
    .bar-label { font-size: 13px; color: #3f3c3d; }
    .bar-track {
      height: 10px;
      border-radius: 999px;
      background: rgba(45, 91, 79, 0.15);
      overflow: hidden;
    }
    .bar-fill {
      height: 10px;
      border-radius: 999px;
      background: linear-gradient(90deg, #2d5b4f, #4a8677);
    }
    .bar-value { font-size: 12px; color: var(--muted); text-align: right; }
    .cta {
      margin-top: 18px;
      border-radius: 16px;
      background: linear-gradient(125deg, #2b4f44, #1f3932);
      color: #f8f7f5;
      padding: 18px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 14px;
      flex-wrap: wrap;
    }
    .cta a {
      text-decoration: none;
      background: var(--sun);
      color: #2a1706;
      font-weight: 700;
      border-radius: 999px;
      padding: 10px 18px;
    }
    .updated { margin-top: 10px; font-size: 12px; color: var(--muted); }
    @media (max-width: 980px) {
      .grid4 { grid-template-columns: repeat(2, 1fr); }
      .grid3 { grid-template-columns: 1fr; }
      .grid2 { grid-template-columns: 1fr; }
    }
    @media (max-width: 620px) {
      .grid4 { grid-template-columns: 1fr; }
      .bar-row { grid-template-columns: 100px 1fr 34px; }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <div class="eyebrow">Rising Sparks Public Dashboard</div>
      <h1>Find your people. Build the city.</h1>
      <p class="sub">
        A live, anonymized view of how signals become introductions across camps, seekers,
        and moderators.
      </p>
      <div class="grid4" id="summary-grid"></div>
    </section>

    <section class="panel">
      <h2 class="section-title">Key Metrics</h2>
      <div class="grid4" id="key-metrics"></div>
    </section>

    <section class="panel">
      <h2 class="section-title">Match Funnel</h2>
      <div class="grid4" id="pipeline"></div>
    </section>

    <section class="panel grid2">
      <div>
        <h2 class="section-title">Live Activity</h2>
        <div class="timeline" id="live-feed"></div>
      </div>
      <div>
        <h2 class="section-title">Where Signals Come From</h2>
        <div class="bars" id="platform-breakdown"></div>
      </div>
    </section>

    <section class="panel grid2">
      <div>
        <h2 class="section-title">Most Requested Skills</h2>
        <div class="bars" id="demand-contrib"></div>
      </div>
      <div>
        <h2 class="section-title">Most Requested Vibes</h2>
        <div class="bars" id="demand-vibes"></div>
      </div>
    </section>

    <section class="cta">
      <div>
        <strong>Help us build this?</strong><br>
        Tell us what feels useful, what’s missing, or what feels too automated.
      </div>
      <a id="feedback-link" href="/forms/">Send Feedback to Organizers</a>
    </section>
    <div class="updated" id="updated"></div>
  </main>

  <script>
    const fmt = (n) => new Intl.NumberFormat().format(n || 0);
    const pct = (x) => `${Math.round((x || 0) * 100)}%`;

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
        <article class="card">
          <div class="kicker">${stage}</div>
          <div class="metric">${fmt(count)}</div>
        </article>
      `;
    }

    function barRow(name, count, max) {
      const w = max > 0 ? Math.max(4, Math.round((count / max) * 100)) : 0;
      return `
        <div class="bar-row">
          <div class="bar-label">${name}</div>
          <div class="bar-track"><div class="bar-fill" style="width:${w}%"></div></div>
          <div class="bar-value">${fmt(count)}</div>
        </div>
      `;
    }

    function eventRow(item) {
      return `
        <div class="event-row">
          <div class="pill">${item.event_type}</div>
          <div class="event-meta">
            ${new Date(item.occurred_at).toLocaleString()} • ${item.platform}
          </div>
          <div class="event-text">${item.summary}</div>
        </div>
      `;
    }

    function renderBars(elId, rows) {
      const el = document.getElementById(elId);
      if (!rows || !rows.length) {
        el.innerHTML = `<p class="note">No data yet.</p>`;
        return;
      }
      const max = Math.max(...rows.map((r) => r.count || 0));
      el.innerHTML = rows.map((r) => barRow(r.name || r.platform, r.count, max)).join("");
    }

    async function load() {
      const res = await fetch("/community/data");
      const data = await res.json();

      const summary = data.summary || {};
      const weekly = data.weekly || {};
      document.getElementById("summary-grid").innerHTML = [
        metricCard(
          "Conversations Heard",
          summary.total_ingested,
          `${fmt(weekly.ingested_7d)} in last 7 days`
        ),
        metricCard(
          "Signals Analyzed",
          summary.indexed,
          `${fmt(weekly.indexed_7d)} in last 7 days`
        ),
        metricCard(
          "Likely Connections",
          summary.proposed_matches,
          `${fmt(weekly.matches_7d)} in last 7 days`
        ),
        metricCard(
          "Handshakes Facilitated",
          summary.intros_sent,
          `${fmt(weekly.intros_7d)} in last 7 days`
        ),
      ].join("");

      const m = data.key_metrics || {};
      document.getElementById("key-metrics").innerHTML = [
        metricCard("Active Camps", m.active_camps, "All-time active profiles"),
        metricCard("Active Seekers", m.active_seekers, "All-time active profiles"),
        metricCard(
          "Conversations Started",
          m.conversation_started_total,
          `Intro→Conversation ${pct(m.intro_to_conversation_rate)}`
        ),
        metricCard(
          "Onboarded",
          m.onboarded_total,
          `Conversation→Onboard ${pct(m.conversation_to_onboarding_rate)}`
        ),
      ].join("");

      document.getElementById("pipeline").innerHTML =
        (data.pipeline || []).map((x) => pipelineCard(x.stage, x.count)).join("");

      const feed = data.live_feed || [];
      document.getElementById("live-feed").innerHTML = feed.length
        ? feed.map((item) => eventRow(item)).join("")
        : `<p class="note">No recent activity in the last 7 days.</p>`;

      renderBars("platform-breakdown", data.platform_breakdown || []);
      renderBars("demand-contrib", (data.demand && data.demand.top_contribution_types) || []);
      renderBars("demand-vibes", (data.demand && data.demand.top_vibes) || []);

      if (data.cta && data.cta.feedback_url) {
        document.getElementById("feedback-link").href = data.cta.feedback_url;
      }

      const backlog = data.backlog || {};
      const backlogText = backlog.oldest_needs_review_age_hours == null
        ? "All current signals are reviewed."
        : `Oldest pending: ${backlog.oldest_needs_review_age_hours}h`;
      document.getElementById("updated").textContent = (
        `Review queue: ${fmt(backlog.needs_review_count)} • ` +
        `${backlogText} • Updated ${new Date(data.updated_at).toLocaleString()}`
      );
    }

    load();
    setInterval(load, 60000);
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
    profiles = (await session.exec(select(Profile))).all()

    intro_terminal = {
        MatchStatus.INTRO_SENT,
        MatchStatus.CONVERSATION_STARTED,
        MatchStatus.ACCEPTED_PENDING,
        MatchStatus.ONBOARDED,
    }
    conversation_terminal = {
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
            (now_naive - oldest.detected_at).total_seconds() / 3600,
            1,
        )

    platform_breakdown = _platform_breakdown(posts)
    structured_count = sum(1 for p in posts if p.status != PostStatus.RAW)

    active_camps = sum(
        1
        for prof in profiles
        if prof.is_active and prof.role == PostRole.CAMP
    )
    active_seekers = sum(
        1
        for prof in profiles
        if prof.is_active and prof.role == PostRole.SEEKER
    )

    conversation_started_total = sum(1 for m in matches if m.status in conversation_terminal)
    onboarded_total = sum(1 for m in matches if m.status == MatchStatus.ONBOARDED)
    intro_to_conversation_rate = (
        conversation_started_total / intros_sent if intros_sent > 0 else 0.0
    )
    conversation_to_onboarding_rate = (
        onboarded_total / conversation_started_total if conversation_started_total > 0 else 0.0
    )

    stories = _build_stories(posts, matches)
    live_feed = _build_live_feed(posts, matches, seven_days_ago)
    demand = _build_demand(posts)
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
        "key_metrics": {
            "active_camps": active_camps,
            "active_seekers": active_seekers,
            "match_attempts_total": len(matches),
            "intro_sent_total": intros_sent,
            "conversation_started_total": conversation_started_total,
            "onboarded_total": onboarded_total,
            "intro_to_conversation_rate": round(intro_to_conversation_rate, 4),
            "conversation_to_onboarding_rate": round(conversation_to_onboarding_rate, 4),
        },
        "platform_breakdown": platform_breakdown,
        "platform_mix": platform_breakdown,
        "pipeline": [
            {"stage": "Heard", "count": total_ingested},
            {"stage": "Analyzed", "count": structured_count},
            {"stage": "Matched", "count": proposed_matches},
            {"stage": "Introduced", "count": intros_sent},
        ],
        "live_feed": live_feed,
        "demand": demand,
        "stories": stories,
        "cta": {"feedback_url": feedback_url},
        "updated_at": now.isoformat(),
    }


def _platform_breakdown(posts: list[Post]) -> list[dict[str, Any]]:
    platform_counts = Counter(p.platform for p in posts)
    total_ingested = len(posts)
    rows: list[dict[str, Any]] = []
    for platform, count in sorted(platform_counts.items(), key=lambda x: x[1], reverse=True):
        pct = round((count / total_ingested) * 100, 1) if total_ingested else 0.0
        rows.append({"platform": platform, "count": count, "pct": pct})
    return rows


def _build_live_feed(
    posts: list[Post],
    matches: list[Match],
    since: datetime,
) -> list[dict[str, Any]]:
    feed: list[dict[str, Any]] = []
    relevant_post_statuses = {PostStatus.INDEXED, PostStatus.NEEDS_REVIEW}

    for post in posts:
        if post.detected_at < since or post.status not in relevant_post_statuses:
            continue
        summary = _sanitize_text(post.raw_text or post.title, max_len=120)
        status_label = "indexed" if post.status == PostStatus.INDEXED else "needs_review"
        feed.append(
            {
                "event_type": f"post_{status_label}",
                "occurred_at": post.detected_at.replace(tzinfo=UTC).isoformat(),
                "platform": post.platform,
                "summary": summary,
            }
        )

    for match in matches:
        if match.created_at >= since:
            feed.append(
                {
                    "event_type": f"match_{match.status}",
                    "occurred_at": match.created_at.replace(tzinfo=UTC).isoformat(),
                    "platform": match.intro_platform or "multi",
                    "summary": _match_summary(match),
                    "score": round(match.score, 3),
                    "confidence": (
                        round(match.confidence, 3)
                        if match.confidence is not None
                        else None
                    ),
                }
            )
        if match.intro_sent_at is not None and match.intro_sent_at >= since:
            feed.append(
                {
                    "event_type": "intro_sent",
                    "occurred_at": match.intro_sent_at.replace(tzinfo=UTC).isoformat(),
                    "platform": match.intro_platform or "multi",
                    "summary": "Moderator-facilitated introduction sent.",
                    "score": round(match.score, 3),
                    "confidence": (
                        round(match.confidence, 3)
                        if match.confidence is not None
                        else None
                    ),
                }
            )

    feed.sort(key=lambda row: row["occurred_at"], reverse=True)
    return feed[:20]


def _build_demand(posts: list[Post]) -> dict[str, list[dict[str, Any]]]:
    statuses = {PostStatus.INDEXED, PostStatus.NEEDS_REVIEW}
    seeker_posts = [
        p
        for p in posts
        if p.role == PostRole.SEEKER and p.status in statuses
    ]

    contrib_counts: Counter[str] = Counter()
    vibe_counts: Counter[str] = Counter()

    for post in seeker_posts:
        contrib_counts.update(post.contribution_types_list())
        vibe_counts.update(post.vibes_list())

    top_contrib = [
        {"name": name, "count": count}
        for name, count in contrib_counts.most_common(10)
    ]
    top_vibes = [
        {"name": name, "count": count}
        for name, count in vibe_counts.most_common(10)
    ]

    return {
        "top_contribution_types": top_contrib,
        "top_vibes": top_vibes,
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
                "title": f"Potential Connection {idx}",
                "problem": _sanitize_text(seeker.raw_text or seeker.title, max_len=140),
                "intervention": f"Found common ground through {overlap_text}.",
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
                "title": f"Active Signal {idx}",
                "problem": _sanitize_text(post.raw_text or post.title, max_len=140),
                "intervention": "Analyzed for alignment with the builder community.",
                "outcome": "Awaiting a likely counterpart.",
                "confidence_note": "Anonymized community signal.",
            }
        )
        if len(story_rows) >= 3:
            break

    return story_rows


def _match_summary(match: Match) -> str:
    if match.status == MatchStatus.PROPOSED:
        return "Potential match added to moderator queue."
    if match.status == MatchStatus.APPROVED:
        return "Potential match approved for intro."
    if match.status in {
        MatchStatus.INTRO_SENT,
        MatchStatus.CONVERSATION_STARTED,
        MatchStatus.ACCEPTED_PENDING,
        MatchStatus.ONBOARDED,
    }:
        return "Potential match moved toward direct connection."
    if match.status == MatchStatus.DECLINED:
        return "Potential match declined after review."
    return "Potential match updated."


def _outcome_label(status: str) -> str:
    if status == MatchStatus.INTRO_SENT:
        return "Handshake facilitated."
    if status == MatchStatus.CONVERSATION_STARTED:
        return "They’re talking."
    if status in {MatchStatus.ACCEPTED_PENDING, MatchStatus.ONBOARDED}:
        return "Aligned for the playa."
    if status == MatchStatus.APPROVED:
        return "Verified for intro."
    return "Awaiting human review."


def _confidence_note(match: Match) -> str:
    if match.confidence is not None:
        return f"Vibe match: {round(match.confidence * 100)}%."
    if match.score:
        return f"Contribution alignment: {round(match.score * 100)}%."
    return "Matched on skills and ethos."


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
