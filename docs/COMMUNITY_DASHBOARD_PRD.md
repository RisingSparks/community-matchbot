# PRD: Community Dashboard Redesign
**Rising Sparks Matchbot — Community-Facing Experience**

**Status:** Draft
**Author:** Product / UX
**Last Updated:** 2026-03-17
**Depends On:** Backend `/community/data` API (existing), Forms router (existing)

---

## Problem Statement

The current community dashboard at `/community/` was designed as an operator view — a window into the bot's pipeline health — and was never fully rethought for the people it's supposed to serve. A first-time seeker arriving from a Reddit thread is greeted by funnel conversion rates, extraction confidence scores, a "Data Nerd View" toggle, and a "Matched Drill-Down" with status dropdowns. The content they actually care about — active camps, seekers, and gear listings — is buried below several dense data sections.

This creates two compounding problems: newcomers bounce without understanding the value or finding anything relevant to them, and the tool's core purpose (connecting humans) is obscured by the infrastructure built to support it. During peak season (March–July), every bounced seeker is a missed connection.

---

## Goals

1. **First-visit comprehension in under 10 seconds.** A newcomer arriving from any referral source should immediately understand what Rising Sparks is and which of the three primary flows (find a camp / find contributors / exchange gear) is relevant to them.

2. **Browse-first, form-second.** Users should be able to explore active listings before being asked to submit anything. The current page leads with a CTA form before any browsable content.

3. **Mobile experience on par with desktop.** At least 60% of community traffic is mobile. The current layout requires horizontal scrolling and has several components with fixed minimum widths that break on small screens.

4. **Transparency preserved, not buried.** The full metrics and pipeline data remain publicly accessible — consistent with community values around radical transparency — but as an intentional destination rather than the default landing experience.

5. **Reduce time-to-relevant-listing.** Measured as the number of interactions (taps/clicks/scrolls) required to reach a browsable list of active camps, seekers, or gear items from a cold page load. Target: ≤ 2 interactions.

---

## Non-Goals

1. **Not a redesign of the moderator dashboard.** The mod UI has its own spec (`MODERATOR_UI_SPEC_v2.md`) and is a separate product with a separate user. This PRD covers only the public-facing community experience.

2. **Not a user account or authentication system.** Users cannot log in, save favorites, or receive notifications through the community dashboard. Authentication is reserved for the moderator tool.

3. **Not a real-time messaging product.** The dashboard surfaces listings and facilitates the matchbot's intro process; it does not enable direct messaging between community members.

4. **Not a migration away from the existing backend API.** The redesigned frontend will consume the same `/community/data` endpoint and existing `/forms/` routes. No backend changes are required as a prerequisite.

5. **Not a native mobile app.** The experience must be mobile-optimized but delivered as a responsive web app (PWA-compatible). No App Store submission is in scope.

---

## User Personas

### Persona A — The Seeker
*"I've been to Burning Man twice, I want to find a camp where I actually fit in."*

- Arrives from a link in a Reddit thread or Discord message
- Has never heard of Rising Sparks before
- Attention span: 60 seconds before they click away
- Knows what vibes/skills they bring; doesn't know the vocabulary of the system
- Needs: a browse experience that lets them scan camps and see themselves reflected

### Persona B — The Camp or Art Lead (TCO)
*"We're building a 40-person camp and need a sound engineer and two kitchen leads."*

- Arrives intentionally — someone mentioned this tool, or they submitted a post themselves
- Repeat visitor during peak season
- Needs: a filtered view of seekers by skill/contribution type; ability to submit their own camp listing
- Pain point: Their time is extremely scarce; irrelevant results are expensive

### Persona C — The Infrastructure Lead
*"We have three shade structures we're not using. Someone needs them."*

- Very specific, transactional need
- Often older burner, less social-media native
- Needs: a clean two-sided board (needs / offers) without noise
- Will not scroll past two sections looking for their content

### Persona D — The Curious Community Member
*"I heard about this matchbot — how does it actually work? Is it trustworthy?"*

- Not necessarily seeking a match themselves
- Wants to understand the system: what data is collected, how decisions are made, what the reach is
- Needs: the transparency/stats view, the "how it works" explainer, clear privacy framing

---

## User Stories

### Seeker (Persona A)
- As a seeker, I want to browse active camp and art project listings so I can find one that matches my vibe and skills without filling out a form first.
- As a seeker, I want to filter listings by vibe tags so I can quickly narrow down to camps that feel right for me.
- As a seeker, I want to see a short snippet of the original post so I can get a sense of the camp's voice before deciding to click through.
- As a seeker, I want a clear CTA to submit my own signal after I've seen what's available.

### Camp / Art Lead (Persona B)
- As a camp lead, I want to browse people who are actively looking for a camp so I can identify potential contributors before they find us.
- As a camp lead, I want to filter seekers by contribution type (e.g., build, kitchen, tech) so I can find people with relevant skills.
- As a camp lead, I want to submit our camp as an available listing directly from the dashboard without having to post in another channel.

### Infrastructure Lead (Persona C)
- As an infra lead, I want to immediately find a clean list of gear needs and gear offers without navigating through mentorship content.
- As an infra lead, I want to see item category, quantity, and condition at a glance so I can evaluate relevance without clicking into each post.

### Curious Community Member (Persona D)
- As a community member, I want to see how many people the bot has connected so I can assess whether it's actually working.
- As a community member, I want to read a plain-language explanation of how the matchmaking works so I know what I'm consenting to if I post.
- As a community member, I want access to the full pipeline metrics so I can verify the system is operating transparently.

---

## Requirements

### P0 — Must Have

#### Navigation
- **NAV-1:** A persistent navigation element (bottom tab bar on mobile, top nav on desktop) with five destinations: Home, Camps & Projects, Seekers, Gear Exchange, Transparency.
  - *Acceptance criteria:* Navigation is visible at all viewport widths ≥ 320px. Active state is always visible. Tab bar is fixed to the bottom of the viewport on mobile (iOS/Android) and does not overlap content.
- **NAV-2:** All five destinations are functional and load distinct page views (client-side routing or separate server routes).
- **NAV-3:** Navigation tabs use human-friendly labels, not system vocabulary. No mention of "mentorship," "infrastructure," "indexed," or "post_type" in any user-facing nav label or heading.

#### Home Page
- **HOME-1:** The hero section communicates the product's purpose in one headline and two sentences, visible without scrolling on a 390px-wide mobile viewport.
- **HOME-2:** Three prominent "entry point" elements below the hero let users self-select their path: (a) Looking for a camp or project, (b) Our camp needs people, (c) Gear & infrastructure exchange. Each links directly to its respective page.
- **HOME-3:** A "season snapshot" shows three human-language numbers: active seekers, active camps/projects, and intros sent this season. No percentages, funnel rates, or confidence scores.
- **HOME-4:** A "recent activity" strip shows 3–5 of the most recently indexed listings as preview cards (camp name or snippet, primary vibe tag, platform badge). These are live data, not static.
- **HOME-5:** A bottom CTA prompts users to submit their own signal, linking to `/forms/`.

#### Camps & Projects Page
- **CAMP-1:** Displays all active (INDEXED) mentorship posts where role = camp, as a card grid.
- **CAMP-2:** Each card shows: camp/project name (or "Anonymous camp" if unknown), up to 3 vibe tags, up to 2 contribution type tags, a 1–2 line snippet from the raw post text, platform badge (Reddit / Discord / Facebook), and a "See original post →" link if a source URL is available.
- **CAMP-3:** Filter chips at the top of the page allow single or multi-select filtering by vibe and contribution type. Chips load from the same taxonomy source as the backend. Selecting a chip filters the displayed cards without a page reload.
- **CAMP-4:** Empty state: "No active camp listings right now. Check back soon — or submit your signal below." with a link to `/forms/`.
- **CAMP-5:** Card grid is single-column on viewports < 640px, two columns on 640–1024px, three columns on > 1024px. No horizontal scrolling on any viewport.

#### Seekers Page
- **SEEK-1:** Displays all active (INDEXED) mentorship posts where role = seeker, as a card grid using the same card format as CAMP-2.
- **SEEK-2:** Each card shows: primary contribution type as the lead label, vibe tags, a 1–2 line snippet, platform badge, and source URL link if available.
- **SEEK-3:** Filter chips allow filtering by contribution type and vibe, identical in behavior to CAMP-3.
- **SEEK-4:** Empty state equivalent to CAMP-4.
- **SEEK-5:** Same responsive grid behavior as CAMP-5.

#### Gear Exchange Page
- **GEAR-1:** Two clearly labeled sections (or tabs on mobile): "What People Need" and "What People Have." On desktop these can render side by side; on mobile they are tabs.
- **GEAR-2:** Each gear item card shows: infra category tag, item description (from snippet), quantity and condition if known, platform badge, and source URL link if available.
- **GEAR-3:** Empty state per section: "Nothing listed here right now."
- **GEAR-4:** No horizontal scrolling on any viewport.

#### Transparency Page
- **TRANS-1:** The full current metrics suite is preserved and accessible here: funnel diagram, alignment snapshot (skills/vibes supply vs demand), matched drill-down with status/time-window filters, live activity feed (Story View and Data Nerd View), platform breakdown, and infrastructure exchange snapshot.
- **TRANS-2:** The page opens with a one-paragraph plain-language header explaining why this data is public and what it represents. Tone: warm, community-native, not corporate. Example: *"We publish everything. Here's a live view of what the bot is actually doing — every post it sees, every match it proposes, every intro it sends."*
- **TRANS-3:** The "Data Nerd View" toggle is retained exactly as it exists today.
- **TRANS-4:** All existing filter controls (status filter, time window) are retained.

#### Mobile
- **MOB-1:** All pages render correctly at 320px minimum viewport width.
- **MOB-2:** All tap targets (buttons, filter chips, card links, nav tabs) are ≥ 44×44px.
- **MOB-3:** No page requires horizontal scrolling on any viewport.
- **MOB-4:** Filter chips scroll horizontally within their container on mobile rather than wrapping to multiple rows.
- **MOB-5:** The bottom tab nav does not obscure content; pages have appropriate bottom padding to account for the nav bar height.

#### Tone & Copy
- **COPY-1:** No system-internal vocabulary in any user-facing string. This includes: confidence, extraction, indexed, NEEDS_REVIEW, SKIPPED, post_type, seeker_intent, age_hours, infra_role.
- **COPY-2:** Section headers are written as natural language, not data table labels.
- **COPY-3:** All empty states are written in first-person community voice, never generic ("No data found").

---

### P1 — Nice to Have

- **P1-1:** PWA manifest + service worker so the site can be added to a phone home screen.
- **P1-2:** A "How It Works" section or page with a 3-step visual explainer (posts are collected → structured by AI → a human reviews and may send an intro) and a brief FAQ covering privacy, opt-out, and the non-official status of Rising Sparks.
- **P1-3:** Vibe tag chips are color-coded consistently across all pages (same tag = same color everywhere).
- **P1-4:** Card snippets truncate gracefully with a "Read more" expand, rather than cutting off mid-sentence.
- **P1-5:** The season snapshot numbers on the Home page animate briefly on load (count-up) to draw attention.
- **P1-6:** The Transparency page is linked from the footer on all pages with a brief label like "Open stats →" so skeptical users can find it without navigating the tab bar.
- **P1-7:** A "last updated" timestamp on each card shows how recently the post was indexed, expressed in natural language ("3 days ago," not a raw datetime).
- **P1-8:** Filter state is preserved in the URL query string so filtered views are shareable.

---

### P2 — Future Considerations

- **P2-1:** A camp or seeker can mark their listing as "no longer looking" via a simple link/form, which triggers a moderation action to remove them from the browse view.
- **P2-2:** A "signal match" feature where a seeker can see which active camps share their top vibes/skills before submitting.
- **P2-3:** Email or Discord notification for seekers when a new camp matching their submitted tags is indexed.
- **P2-4:** Dark mode.
- **P2-5:** Localization / non-English support.

---

## Information Architecture

```
/ (Home)
├── /community/camps         → Camps & Projects browse
├── /community/seekers       → Builders & Seekers browse
├── /community/gear          → Gear Exchange
├── /community/transparency  → Open stats / full metrics (current dashboard content)
├── /community/how-it-works  → Explainer + FAQ (P1)
└── /forms/                  → Submit your signal (existing)
```

The existing `/community/` route becomes the new Home. The Transparency page replaces the current monolithic dashboard as the metrics destination.

---

## Visual Design Direction

### Keep
- Desert color palette: `--sand` (#f5f0e8), `--sage` (#2d5b4f), `--sun` (#e8a04a), `--ink` (#221E21), `--card` (#fffdf8)
- Rounded card aesthetic (border-radius: 14–20px)
- The hero headline: "Find your people. Build the city."
- Warm, slightly rough texture implied by the color palette — not a cold tech product

### Change
- Lead with cards and listings, not charts and tables
- Font size hierarchy: post snippets at ≥ 16px for readability (currently 12–13px in some sections)
- Replace all data tables in the public pages (Camps, Seekers, Gear) with card grids
- Platform badge as a small colored pill (Reddit = orange, Discord = indigo, Facebook = blue) rather than monospace text
- Vibe and contribution-type tags as warm colored pills — not mono uppercase labels

### Mobile-First Layout Decisions
- Bottom tab bar: 64px height, icon + label, five tabs
- Card grid: 100% width cards on mobile with 16px horizontal padding
- Filter chip row: horizontally scrollable, no line wrapping, 8px gap between chips
- Hero entry points: stacked full-width buttons on mobile (not a 3-column grid)

---

## Success Metrics

### Leading Indicators (measurable immediately after launch)

| Metric | Baseline | Target |
|--------|----------|--------|
| Bounce rate from `/community/` home | TBD (measure at launch) | < 50% |
| % of sessions that reach a browse page (Camps, Seekers, or Gear) | TBD | > 40% |
| % of sessions on mobile with horizontal scroll events | TBD | < 5% |
| Avg. interactions to reach first listing | ~5 (estimated) | ≤ 2 |
| Transparency page views as % of total sessions | N/A (new destination) | > 10% |

### Lagging Indicators (measurable over peak season)

| Metric | Target |
|--------|--------|
| Form submissions via `/forms/` per week during March–July | +20% vs prior season |
| Seeker posts submitted (not just Reddit/Discord scraped) | Establish baseline |
| Moderator queue age stays < 48 hrs | Unchanged (mod dashboard dependency) |
| Qualitative: community feedback on tool usefulness | Positive sentiment in BM community channels |

---

## Open Questions

| # | Question | Owner | Priority |
|---|----------|-------|----------|
| OQ-1 | Does the existing `/community/data` API endpoint return all the fields needed for the new card format (snippet, source URL, platform, vibes, contribution types)? Or does it need a new/extended endpoint? | Engineering | P0 blocker |
| OQ-2 | Should the Transparency page live at `/community/transparency` (same server, same router) or at the existing `/community/` URL with a tab/toggle? Routing strategy affects how existing links shared by community members behave. | Engineering + Product | P0 |
| OQ-3 | What is the snippet source for cards? The raw post text (first N chars)? A generated summary? This affects both the backend API and card readability. | Engineering | P0 |
| OQ-4 | How many active indexed listings are there currently? If the pool is very small (< 10), the browse pages will feel empty immediately post-launch and need strong empty-state handling. | Data / Engineering | P1 |
| OQ-5 | Is there a preferred framework decision for this frontend? The mod UI spec recommends React + Vite + Tailwind — should the community dashboard use the same stack and repo, or stay as server-rendered HTML in the FastAPI router? | Engineering | P1 |
| OQ-6 | Privacy check: do the card snippets (raw post text) constitute PII? Are there cases where a seeker's raw post text contains their real name, contact info, or other identifying detail that shouldn't be surfaced without a click-through to the original source? | Product + Legal/Privacy | P0 |
| OQ-7 | Should the "How It Works" page be a standalone page or a section at the bottom of the Home page? Depends on how much copy the team wants to write and how discoverable it needs to be. | Product + Design | P2 |

---

## Timeline Considerations

**Hard deadline: Peak season begins in earnest around April 1.** Any improvement to the community-facing experience needs to ship before the volume of seekers and camps increases significantly.

**Suggested phasing:**

### Phase 1 — MVP (target: before April 1)
- New multi-page navigation structure
- Home page with entry points and season snapshot
- Camps & Projects browse page
- Seekers browse page
- Gear Exchange page
- Transparency page (migrates current dashboard content verbatim — no visual change needed for Phase 1)
- All P0 mobile requirements

### Phase 2 — Polish (target: mid-April)
- Filter chips with URL state persistence (P1-8)
- "How It Works" page (P1-2)
- Consistent vibe tag color system (P1-3)
- "Last updated" natural language timestamps (P1-7)
- PWA manifest (P1-1)

### Phase 3 — Future season
- P2 items as prioritized by community feedback

---

## Appendix: Copy Reference

**Home hero headline:** "Find your people. Build the city."

**Home subheadline:** "A community matchmaking experiment — surfacing camps, projects, and infrastructure across the ecosystem."

**Entry point labels:**
- "Looking for a camp or project"
- "Our camp or project needs people"
- "Gear & infrastructure exchange"

**Season snapshot labels:** "[N] seekers active" / "[N] camps & projects" / "[N] intros sent this season"

**Transparency page header:** *"We publish everything. Here's a live view of what the bot is actually doing — every post it sees, every match it proposes, every intro it sends. Rising Sparks operates with full transparency because trust is the whole point."*

**Camps page header:** "Active camps and projects looking for contributors this season."

**Seekers page header:** "People looking for their camp or project this season."

**Gear page header:** "Gear, structures, and equipment — what the community needs and what's available."

**Empty state (generic):** "Nothing here right now — check back soon, or [submit your signal →]."

---

*Rising Sparks is a volunteer-led community experiment. This is not an official Burning Man Project initiative.*
