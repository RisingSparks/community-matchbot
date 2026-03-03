# Moderator Review UI — Spec

Mobile-optimized web app for triaging posts in `NEEDS_REVIEW` status.

## What it is

A triage tool, not a data browser. The moderator works through a queue of
posts the LLM wasn't confident about. Per post: read the raw text, check what
was extracted, then approve / fix-and-approve / dismiss. The UI should be
optimized for moving through that queue quickly.
The queue includes camp-finding, art-project-finding, and builder-seeking
posts.

---

## Screens

| Screen | Purpose |
|--------|---------|
| Home | Queue count, "Start Reviewing" CTA, recent activity |
| Queue card | Main triage UI — one post at a time, progress indicator |
| Edit sheet | Bottom sheet for field corrections before approving |
| Post list | Browse all posts with filters, jump to specific posts |
| Post detail | Read-only full view of any post + event log |
| Settings | Auth, notification prefs |

---

## Functional requirements

### Queue management
- Display how many posts are waiting (badge/count visible immediately on open)
- Filter by post type (mentorship vs infrastructure) and platform
- Default sort: oldest first (so nothing rots)

### Per-post review
- Show raw text prominently — this is the moderator's ground truth
- Show extracted fields alongside with visual confidence indicators
- Highlight fields with low confidence (most likely wrong)
- Three actions: **Approve** / **Edit & Approve** / **Dismiss**
- Re-extract as an escape hatch ("let the LLM try again")

### Field editing
- Vibes and contribution_types: multi-select chip pickers (constrained taxonomy)
- Role: 3-way toggle — seeker / camp-or-art-project / unknown
- Free-text fields (camp/project name, quantity, condition): simple text inputs
- Infra fields (infra_role, infra_categories) shown only for infrastructure posts

### Dismiss
- Required reason selection: Spam / Off-topic / Duplicate / Not a real post / Other
- Optional free-text note

### Approve
- Optional note field
- If fields were edited, show a summary of changes before confirming

### Undo
- 5-second toast with Undo after approve or dismiss
- Covers mobile misclicks

### Audit
- Every action writes an Event record with actor and optional note (already
  implemented in backend CLI)

---

## Interaction model

**Card-based, one at a time.** Default entry point is the queue card ("3 of
12"), not a list. The post list exists for browsing/filtering but isn't the
primary triage surface.

**Explicit buttons, not swipe-only.** Swipe gestures are a shortcut, not the
primary affordance — moderation decisions have real consequences.

**Edit via bottom sheet.** Tapping "Edit & Approve" slides up a bottom sheet
with all editable fields. The raw text remains partially visible behind it.
"Confirm & Approve" lives at the bottom of the sheet.

---

## Layout: raw text vs extracted fields

Stacked layout:
1. Extracted fields (compact chips/tags) at top
2. Raw text below — first ~300 chars shown, expandable

Both visible without switching tabs. Raw text is always reachable.

**Critical:** raw text must be highly readable — adequate font size, good
contrast, appropriate line length. Everything else is secondary to this.

---

## Taxonomy pickers

Vibes and contribution_types are loaded from the server (or bundled at build
time). Rendered as multi-select chip grids — one tap per tag. Not free text.

---

## Authentication

Simple shared secret or magic link (email). No OAuth, no Discord integration.

**Decision:** choose one:
- **Shared password** — simplest, good for a single-person mod team
- **Magic link** — passwordless email, slightly more secure, better for a
  small team where the password would otherwise be shared in plaintext

---

## Real-time / multi-moderator

Optimistic, last-write-wins for now. If two moderators submit conflicting
actions on the same post, the backend returns an error ("post is no longer in
NEEDS_REVIEW") and the UI shows a clear message. No soft-locking needed at
this scale.

---

## Platform

**PWA (web app with manifest + service worker).** No app store, works on any
phone, can be installed to home screen. React + a lightweight backend (or the
existing FastAPI server).

---

## Notifications

Push notification or daily summary when the NEEDS_REVIEW queue grows past a
threshold (e.g. 5 posts). Could be a Discord message to the mod channel
instead of a push notification — simpler to implement.

---

## Out of scope (for now)

- Dark mode
- Native mobile app
- Moderator role management / permissions
- Bulk approve/dismiss
