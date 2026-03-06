"""Public community showcase page and data endpoint."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
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
    .tab-bar {
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }
    .tab-btn {
      border: 1px solid rgba(45, 91, 79, 0.35);
      background: #ffffff;
      color: var(--ink);
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }
    .tab-btn[aria-selected="true"] {
      background: rgba(45, 91, 79, 0.14);
      border-color: rgba(45, 91, 79, 0.6);
    }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }
    .table-wrap {
      overflow-x: auto;
      border-radius: 12px;
      border: 1px solid rgba(45, 91, 79, 0.2);
      background: #ffffff;
    }
    .data-table {
      width: 100%;
      border-collapse: collapse;
      min-width: 760px;
      font-size: 13px;
    }
    .data-table th,
    .data-table td {
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid rgba(45, 91, 79, 0.15);
      vertical-align: top;
    }
    .data-table th {
      font-size: 12px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--muted);
      background: rgba(45, 91, 79, 0.08);
      position: sticky;
      top: 0;
    }
    .data-table tr:last-child td { border-bottom: none; }
    .mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 12px;
    }
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

    <section class="panel">
      <h2 class="section-title">Matched Drill-Down</h2>
      <div class="grid2" style="margin-bottom: 10px;">
        <label class="note">
          Status
          <select id="match-status-filter">
            <option value="all" selected>All statuses</option>
            <option value="proposed">Proposed</option>
            <option value="approved">Approved</option>
            <option value="intro_sent">Intro sent</option>
            <option value="conversation_started">Conversation started</option>
            <option value="accepted_pending">Accepted pending</option>
            <option value="onboarded">Onboarded</option>
            <option value="declined">Declined</option>
            <option value="closed_stale">Closed stale</option>
          </select>
        </label>
        <label class="note">
          Time window
          <select id="match-days-filter">
            <option value="7">Last 7 days</option>
            <option value="30" selected>Last 30 days</option>
            <option value="90">Last 90 days</option>
            <option value="all">All time</option>
          </select>
        </label>
      </div>
      <div class="grid4" id="matched-summary"></div>
      <div class="timeline" id="matched-list"></div>
    </section>

    <section class="panel grid2">
      <div>
        <h2 class="section-title">Live Activity</h2>
        <div class="tab-bar" role="tablist" aria-label="Live activity views">
          <button
            type="button"
            class="tab-btn"
            id="live-view-story"
            data-target="live-feed-panel"
            aria-selected="true"
          >
            Story View
          </button>
          <button
            type="button"
            class="tab-btn"
            id="live-view-table"
            data-target="live-feed-table-panel"
            aria-selected="false"
          >
            Data Nerd View
          </button>
        </div>
        <div class="tab-pane active" id="live-feed-panel">
          <div class="timeline" id="live-feed"></div>
        </div>
        <div class="tab-pane" id="live-feed-table-panel">
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Occurred At</th>
                  <th>Type</th>
                  <th>Platform</th>
                  <th>Summary</th>
                  <th>Score</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody id="live-feed-table"></tbody>
            </table>
          </div>
        </div>
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

    const funnelStageNotes = {
      Seen: "Public posts ingested from configured channels.",
      Analyzed: "Signals that moved beyond raw ingestion.",
      Matched: "Potential seeker-camp connections created.",
      Introduced: "Connections where an intro was sent.",
    };

    function pipelineCard(stage, count) {
      const note = funnelStageNotes[stage] || "";
      return `
        <article class="card">
          <div class="kicker">${stage}</div>
          <div class="metric">${fmt(count)}</div>
          <p class="note">${note}</p>
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

    function feedTableRow(item) {
      const score = item.score == null ? "n/a" : item.score.toFixed(3);
      const confidence = item.confidence == null
        ? "n/a"
        : `${Math.round(item.confidence * 100)}%`;
      return `
        <tr>
          <td class="mono">${new Date(item.occurred_at).toLocaleString()}</td>
          <td><span class="pill">${item.event_type}</span></td>
          <td>${item.platform || "n/a"}</td>
          <td>${item.summary || ""}</td>
          <td class="mono">${score}</td>
          <td class="mono">${confidence}</td>
        </tr>
      `;
    }

    function setLiveActivityTab(targetId) {
      const panes = ["live-feed-panel", "live-feed-table-panel"];
      const buttons = [
        document.getElementById("live-view-story"),
        document.getElementById("live-view-table"),
      ];
      for (const paneId of panes) {
        const pane = document.getElementById(paneId);
        pane.classList.toggle("active", paneId === targetId);
      }
      for (const btn of buttons) {
        const isActive = btn.dataset.target === targetId;
        btn.setAttribute("aria-selected", isActive ? "true" : "false");
      }
    }

    function matchedRow(item) {
      const confidence = item.confidence == null ? "n/a" : `${Math.round(item.confidence * 100)}%`;
      const score = item.score == null ? "n/a" : item.score.toFixed(3);
      const seekerLink = item.seeker_source_url
        ? (
          `<a href="${item.seeker_source_url}" target="_blank" rel="noopener noreferrer">` +
          `Seeker source</a>`
        )
        : "Seeker source: n/a";
      const campLink = item.camp_source_url
        ? (
          `<a href="${item.camp_source_url}" target="_blank" rel="noopener noreferrer">` +
          `Camp source</a>`
        )
        : "Camp source: n/a";

      return `
        <div class="event-row">
          <div class="pill">match_${item.status}</div>
          <div class="event-meta">
            ${new Date(item.created_at).toLocaleString()} •
            ${item.seeker_platform} → ${item.camp_platform}
          </div>
          <div class="event-text">
            Score ${score} • Confidence ${confidence} • Shared: ${item.shared_signals}
          </div>
          <div class="event-text"><strong>Seeker:</strong> ${item.seeker_summary}</div>
          <div class="event-text"><strong>Camp:</strong> ${item.camp_summary}</div>
          <div class="event-meta">${seekerLink} • ${campLink}</div>
        </div>
      `;
    }

    async function loadMatches() {
      const status = document.getElementById("match-status-filter").value || "all";
      const days = document.getElementById("match-days-filter").value || "30";
      const qs = new URLSearchParams({ status, days, limit: "50" });
      const res = await fetch(`/community/api/matches?${qs.toString()}`);
      const data = await res.json();
      const rows = data.matched || [];
      const byStatus = (data.summary && data.summary.by_status) || {};
      const introSentPlus =
        (byStatus.intro_sent || 0) +
        (byStatus.conversation_started || 0) +
        (byStatus.accepted_pending || 0) +
        (byStatus.onboarded || 0);

      document.getElementById("matched-summary").innerHTML = [
        metricCard(
          "Filtered Total",
          (data.summary && data.summary.total) || 0,
          "Within current filters"
        ),
        metricCard("Proposed", byStatus.proposed || 0, "Potential matches awaiting action"),
        metricCard("Approved", byStatus.approved || 0, "Ready for introductions"),
        metricCard("Intro Sent+", introSentPlus, "Intro sent or further progressed"),
      ].join("");

      document.getElementById("matched-list").innerHTML = rows.length
        ? rows.map((item) => matchedRow(item)).join("")
        : `<p class="note">No matches for current filters.</p>`;
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
          "Conversations Seen",
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
      document.getElementById("live-feed-table").innerHTML = feed.length
        ? feed.map((item) => feedTableRow(item)).join("")
        : `<tr><td colspan="6" class="note">No recent activity in the last 7 days.</td></tr>`;

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

      await loadMatches();
    }

    document.getElementById("match-status-filter").addEventListener("change", loadMatches);
    document.getElementById("match-days-filter").addEventListener("change", loadMatches);
    document.getElementById("live-view-story").addEventListener("click", () => {
      setLiveActivityTab("live-feed-panel");
    });
    document.getElementById("live-view-table").addEventListener("click", () => {
      setLiveActivityTab("live-feed-table-panel");
    });
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


@router.get("/api/overview")
async def community_api_overview(session: AsyncSession = Depends(_get_session)) -> dict[str, Any]:
    payload = await build_public_community_payload(session)
    return {
        "summary": payload["summary"],
        "weekly": payload["weekly"],
        "backlog": payload["backlog"],
        "updated_at": payload["updated_at"],
    }


@router.get("/api/metrics")
async def community_api_metrics(session: AsyncSession = Depends(_get_session)) -> dict[str, Any]:
    payload = await build_public_community_payload(session)
    return {
        "key_metrics": payload["key_metrics"],
        "updated_at": payload["updated_at"],
    }


@router.get("/api/pipeline")
async def community_api_pipeline(session: AsyncSession = Depends(_get_session)) -> dict[str, Any]:
    payload = await build_public_community_payload(session)
    return {
        "pipeline": payload["pipeline"],
        "updated_at": payload["updated_at"],
    }


@router.get("/api/platforms")
async def community_api_platforms(session: AsyncSession = Depends(_get_session)) -> dict[str, Any]:
    payload = await build_public_community_payload(session)
    return {
        "platform_breakdown": payload["platform_breakdown"],
        "updated_at": payload["updated_at"],
    }


@router.get("/api/feed")
async def community_api_feed(session: AsyncSession = Depends(_get_session)) -> dict[str, Any]:
    payload = await build_public_community_payload(session)
    return {
        "live_feed": payload["live_feed"],
        "updated_at": payload["updated_at"],
    }


@router.get("/api/demand")
async def community_api_demand(session: AsyncSession = Depends(_get_session)) -> dict[str, Any]:
    payload = await build_public_community_payload(session)
    return {
        "demand": payload["demand"],
        "updated_at": payload["updated_at"],
    }


@router.get("/api/matches")
async def community_api_matches(
    status: str = Query(default="all"),
    days: str = Query(default="30"),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(_get_session),
) -> dict[str, Any]:
    now = datetime.now(UTC).replace(tzinfo=None)
    posts = (await session.exec(select(Post))).all()
    matches = (await session.exec(select(Match))).all()
    return _build_matches_payload(posts, matches, now, status=status, days=days, limit=limit)


@router.get("/api/stories")
async def community_api_stories(session: AsyncSession = Depends(_get_session)) -> dict[str, Any]:
    payload = await build_public_community_payload(session)
    return {
        "stories": payload["stories"],
        "updated_at": payload["updated_at"],
    }


def _build_matches_payload(
    posts: list[Post],
    matches: list[Match],
    now: datetime,
    *,
    status: str,
    days: str,
    limit: int,
) -> dict[str, Any]:
    allowed_statuses = {
        "all",
        MatchStatus.PROPOSED,
        MatchStatus.APPROVED,
        MatchStatus.INTRO_SENT,
        MatchStatus.CONVERSATION_STARTED,
        MatchStatus.ACCEPTED_PENDING,
        MatchStatus.ONBOARDED,
        MatchStatus.DECLINED,
        MatchStatus.CLOSED_STALE,
    }
    window_days = {"7": 7, "30": 30, "90": 90, "all": None}

    status_value = status if status in allowed_statuses else "all"
    days_value = days if days in window_days else "30"
    since = (
        None
        if window_days[days_value] is None
        else now - timedelta(days=window_days[days_value])
    )

    post_by_id = {post.id: post for post in posts}
    filtered_matches: list[Match] = []
    for match in matches:
        seeker = post_by_id.get(match.seeker_post_id)
        camp = post_by_id.get(match.camp_post_id)
        if seeker is None or camp is None:
            continue
        if status_value != "all" and match.status != status_value:
            continue
        if since is not None and match.created_at < since:
            continue
        filtered_matches.append(match)

    filtered_matches.sort(key=lambda row: row.created_at, reverse=True)
    by_status = dict(Counter(match.status for match in filtered_matches))

    rows: list[dict[str, Any]] = []
    for match in filtered_matches[:limit]:
        seeker = post_by_id[match.seeker_post_id]
        camp = post_by_id[match.camp_post_id]
        overlap = sorted(
            set(seeker.contribution_types_list()).intersection(camp.contribution_types_list())
        )
        rows.append(
            {
                "match_id": match.id,
                "created_at": match.created_at.replace(tzinfo=UTC).isoformat(),
                "status": match.status,
                "score": round(match.score, 3),
                "confidence": round(match.confidence, 3) if match.confidence is not None else None,
                "seeker_platform": seeker.platform,
                "camp_platform": camp.platform,
                "seeker_summary": _sanitize_text(seeker.raw_text or seeker.title, max_len=120),
                "camp_summary": _sanitize_text(camp.raw_text or camp.title, max_len=120),
                "shared_signals": (
                    ", ".join(overlap[:3]) if overlap else "shared contribution signals"
                ),
                "seeker_source_url": seeker.source_url,
                "camp_source_url": camp.source_url,
            }
        )

    return {
        "matched": rows,
        "summary": {
            "total": len(filtered_matches),
            "by_status": by_status,
        },
        "updated_at": now.replace(tzinfo=UTC).isoformat(),
    }


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
            {"stage": "Seen", "count": total_ingested},
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

    for post in posts:
        if post.detected_at < since or post.status != PostStatus.NEEDS_REVIEW:
            continue
        summary = _sanitize_text(post.raw_text or post.title, max_len=120)
        occurred_at = (post.source_created_at or post.detected_at).replace(tzinfo=UTC).isoformat()
        feed.append(
            {
                "event_type": "post_needs_review",
                "occurred_at": occurred_at,
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
