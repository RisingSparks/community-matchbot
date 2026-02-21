# Moderator Review UI — Spec v2

## Why this exists

The matchbot monitors Reddit, Discord, and Facebook for camp-finding and
builder-seeking posts, extracts structured data via LLM, and proposes matches
between seekers and camps. When extraction confidence is low, a post lands in
`NEEDS_REVIEW` instead of the live index.

**Moderators are the quality gate between LLM output and real human
introductions.** A post stuck in `NEEDS_REVIEW` is a potential match that
never happens. A bad post approved carelessly is a mismatch intro that wastes
a TCO's time — and TCO time is the scarcest resource in the system.

The UI must make it fast and easy to clear the queue correctly.

---

## Business context

This is a **pilot**. The moderator team is small — likely 1-3 volunteers, not
a scaled ops center. The workflows must be low-overhead by design (a product
principle from the briefing book: *"workflows must save time for TCOs and
moderators, not add process debt"*).

**Seasonal urgency.** Most seeking/offering activity happens March–July in the
run-up to Burning Man. Posts have real expiration pressure. A queue that rots
for two weeks during peak season means real seekers and camps miss each other.
The UI should surface queue age prominently and make it easy to move fast.

**Two failure modes, both matter:**
- **False positive** — bad post approved, bad intro sent, TCO's time wasted,
  trust eroded.
- **False negative** — good post stuck, intro never sent, seeker misses their
  camp, builder pipeline fails.

Over-moderating is as harmful as under-moderating.

**Tone.** This is a community tool, not a corporate content moderation
dashboard. The UI should feel warm and human — consistent with the product
principle that the bot "facilitates introductions; people build trust." Copy
and visual design should not feel like a tech-company ops tool.

---

## Who the moderator is

From the briefing book (User Type D: Moderators / Community Admins):

- Volunteer role, not a job
- Cares about keeping channels organized and useful
- Pain points: high moderation overhead, inconsistent post formats, difficulty
  maintaining one source of truth
- Job to be done: reduce duplicate/low-context posts, improve discoverability
  without heavy manual curation

The UI should minimize cognitive load. The moderator is not a power user; they
may visit the queue a few times a week, not daily.

---

## What the moderator does per post

1. Read the raw text (ground truth — what the person actually posted)
2. Check what the LLM extracted and why it was flagged (confidence score)
3. Decide one of:
   - **Approve** — extraction is good enough, index the post
   - **Edit & Approve** — fix one or two fields, then index
   - **Dismiss** — spam, off-topic, duplicate, or genuinely not indexable
   - **Re-extract** — LLM got it badly wrong; try again (escape hatch)

This is a triage workflow. The UI should be optimized for speed and accuracy
through that decision tree, not for browsing or administration.

---

## Screens

| Screen | Purpose |
|--------|---------|
| Home | Queue count + age, "Start Reviewing" CTA, recent activity |
| Queue card | Main triage UI — one post at a time, progress indicator |
| Edit sheet | Bottom sheet for field corrections before approving |
| Post list | Browse all posts with filters (for non-queue use) |
| Post detail | Read-only full view of any post + event history |
| Settings | Auth, notification preferences |

---

## Functional requirements

### Queue management
- Display how many posts are waiting and the age of the oldest post
- Filter by post type (mentorship vs infrastructure) and platform
- Default sort: oldest first — nothing should rot during peak season
- Queue count visible immediately on open, without navigating

### Per-post review
- Show raw text prominently — this is the moderator's ground truth
- Show extracted fields alongside with visual confidence indicators
- Highlight fields with low confidence (most likely wrong)
- Show why it was flagged: confidence score + which fields scored low
- Four actions: **Approve** / **Edit & Approve** / **Dismiss** / **Re-extract**

### Field editing
- Vibes and contribution_types: multi-select chip pickers (constrained to
  taxonomy — never free text for these fields)
- Role: 3-way toggle — seeker / camp / unknown
- Free-text fields (camp_name, quantity, condition, notes): simple text inputs
- Infrastructure fields (infra_role, infra_categories) shown only for
  infrastructure-type posts
- Moderator can add an optional note to any action (audit trail)

### Dismiss
- Required reason: Spam / Off-topic / Duplicate / Not a real post / Other
- Optional free-text elaboration
- Dismissing sends post to `SKIPPED` and writes an event record

### Approve
- Promotes `NEEDS_REVIEW → INDEXED` and immediately triggers match proposals
- Optional note
- If fields were edited, show a summary of changes before confirming

### Undo
- 5-second toast with Undo after approve or dismiss
- Covers mobile misclicks; critical given the volunteer/casual usage pattern

### Audit trail
- Every moderator action writes an Event record with actor + optional note
- Already implemented in backend; UI surfaces event history in post detail view

---

## Interaction model

**Card-based, one at a time.** Default entry point is the queue card showing
progress ("3 of 12"), not a list view. The list exists for browsing but is not
the primary triage surface.

**Explicit buttons, not swipe-only.** Swipe gestures are an optional shortcut;
labeled buttons are the primary affordance. A mismatch intro wastes a real
person's time — the action shouldn't be accidental.

**Edit via bottom sheet.** Tapping "Edit & Approve" slides up a bottom sheet
with all editable fields. The raw text remains partially visible behind it for
reference. "Confirm & Approve" lives at the bottom of the sheet.

---

## Layout: raw text vs extracted fields

Stacked layout, top to bottom:
1. **Post metadata** — platform, community, detected date, confidence score
2. **Extracted fields** — compact chips/tags showing role, vibes, contribution
   types, camp name, etc.
3. **Raw text** — first ~300 chars shown, "Read more" expands to full text
4. **Action bar** — Approve / Edit & Approve / Dismiss / Re-extract

**Critical:** raw text must be highly readable. Adequate font size (≥16px),
high contrast, appropriate line length. A moderator who can't read the post
can't make a good decision. Every other design decision is secondary to this.

---

## Taxonomy pickers

Vibes and contribution_types are loaded from the server at startup (or bundled
at build time from the same `taxonomy.yaml` the backend uses — single source
of truth). Rendered as multi-select chip grids. One tap per tag. Not free text.
Unknown values entered by the LLM are surfaced as warnings, not silently
dropped.

---

## Authentication

Simple and low-friction — this is a volunteer tool with a small moderator team.

**Options (pick one):**
- **Shared password** — simplest to implement, fine for a single moderator
- **Magic link (email)** — passwordless, better for a small team where a
  shared password would otherwise be pasted in plaintext somewhere

No OAuth, no Discord integration, no role management in v1.

---

## Real-time / multi-moderator

Optimistic, last-write-wins. At pilot scale, multi-moderator collisions are
rare. If two moderators act on the same post simultaneously, the backend
returns an error ("post is no longer in NEEDS_REVIEW") and the UI shows a
clear message. No soft-locking needed.

---

## Platform

**PWA** (progressive web app with manifest + service worker). No app store,
works on any phone, can be installed to home screen. Consistent with the
product principle of using lightweight tooling before building dedicated
platforms.

Backend: the existing FastAPI server (`src/matchbot/server.py`) extended with
moderator API endpoints. No separate backend service.

---

## Notifications

When the NEEDS_REVIEW queue exceeds a threshold (suggested: 5 posts, or any
post older than 48 hours during peak season), notify the mod team. Options:
- Discord message to a mod channel (simplest — moderators are already there)
- Email
- Push notification via service worker

Discord message is the most consistent with the "use existing channels first"
product principle.

---

## Copy and tone guidelines

Consistent with the project's messaging guardrails:

- Warm and community-native, never corporate
- Action labels: "Approve" not "Accept"; "Dismiss" not "Reject"
- Empty queue state: celebrate it ("Queue is clear — nice work")
- Avoid language that implies automated ranking or endorsement
- The moderator's role is quality assurance, not gatekeeper — framing matters

---

## Success criteria for the UI

- Moderator can clear a 10-post queue in under 15 minutes
- Zero accidental approvals/dismissals that couldn't be undone
- Moderator confidence: they feel they have enough context per post to make
  a good call without opening the original source thread
- Queue age stays below 48 hours during peak season (March–July)

---

## Out of scope (v1)

- Dark mode
- Native mobile app
- Moderator role management / permissions
- Bulk approve/dismiss
- Analytics dashboard (use existing CLI report commands)
- BMP integration or external stakeholder access
