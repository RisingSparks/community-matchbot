# Mod API — Match Queue Endpoints

## Overview

The moderator API lives at `/api/mod`. All endpoints require the `mod_session` cookie set by the login flow (handled separately). In dev mode with no `MOD_SECRET_KEY` env var, auth is disabled.

The **match queue flow** is:

```
propose_matches()                ← automatic after a post is approved
    ↓
PROPOSED  →  (mod reviews intro draft)
    ↓ approve / decline
APPROVED  →  send-intro
    ↓
INTRO_SENT
```

---

## Authentication

All match endpoints need the `mod_session` cookie. If missing/expired the server returns `401`.

---

## Endpoints

### `GET /api/mod/matches`

List matches in the queue. Defaults to `status=proposed`.

**Query params**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `status` | string | `proposed` | One of: `proposed`, `approved`, `declined`, `intro_sent`, `conversation_started`, `accepted_pending`, `onboarded`, `closed_stale` |
| `limit` | int | `50` | Max results |

**Response** — `200 OK` — array of [Match objects](#match-object)

```json
[
  {
    "id": "abc123",
    "status": "proposed",
    "score": 0.72,
    "score_breakdown": { "vibes": 0.8, "contribution": 0.6 },
    "match_method": "deterministic",
    "confidence": 0.72,
    "moderator_notes": null,
    "mismatch_reason": null,
    "intro_draft": "Hey! We think you two might be a great fit...",
    "intro_sent_at": null,
    "intro_platform": null,
    "created_at": "2025-07-15T10:23:00",
    "seeker": { ... },
    "camp": { ... }
  }
]
```

Note: the `camp` object is the offer-side post for mentorship matches and may
represent either a camp or an art project.

---

### `GET /api/mod/matches/{match_id}`

Full detail for a single match including the intro draft and both posts.

**Response** — `200 OK` — single [Match object](#match-object)

**Errors**
- `404` — match not found

---

### `POST /api/mod/matches/{match_id}/approve`

Approve a proposed match. Transitions `proposed → approved`.

**Request body** (JSON)

```json
{
  "note": "Great fit — same vibes and both do fire art"
}
```

All fields are optional.

**Response** — `200 OK`

```json
{
  "ok": true,
  "match_id": "abc123",
  "new_status": "approved"
}
```

**Errors**
- `404` — match not found
- `409` — invalid transition (e.g., already declined)

---

### `POST /api/mod/matches/{match_id}/decline`

Decline a match. Transitions `proposed → declined` or `approved → declined`.

**Request body** (JSON)

```json
{
  "reason": "Seeker is infrastructure-focused, offer-side post is mentorship-only"
}
```

All fields are optional.

**Response** — `200 OK`

```json
{
  "ok": true,
  "match_id": "abc123",
  "new_status": "declined"
}
```

**Errors**
- `404` — match not found
- `409` — invalid transition (e.g., already sent)

---

### `POST /api/mod/matches/{match_id}/send-intro`

Send the intro message. Match **must be `approved`** first. Transitions `approved → intro_sent`.

**Query params**

| Param | Type | Default |
|-------|------|---------|
| `dry_run` | bool | `false` |

**Request body** (JSON)

```json
{
  "platform": "reddit"
}
```

`platform` is optional — defaults to the seeker's platform. Valid values: `reddit`, `discord`, `facebook`.

**Response (live send)** — `200 OK`

```json
{
  "ok": true,
  "match_id": "abc123",
  "platform": "reddit"
}
```

**Response (dry run)** — `200 OK`

```json
{
  "dry_run": true,
  "platform": "reddit",
  "intro_text": "Hey u/seeker_username! ..."
}
```

**Errors**
- `404` — match not found
- `409` — match is not in `approved` status
- `500` — seeker or offer-side post could not be loaded

---

## Match Object

Both list and detail endpoints return the same shape:

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Match ID |
| `status` | string | See status values above |
| `score` | float | 0–1 composite similarity score |
| `score_breakdown` | object | Per-dimension scores (vibes, contribution, etc.) |
| `match_method` | string | `deterministic` or `deterministic_infra` |
| `confidence` | float \| null | Same as score for deterministic matches |
| `moderator_notes` | string \| null | Internal notes; `[needs LLM triage]` if in triage band |
| `mismatch_reason` | string \| null | Set when declining |
| `intro_draft` | string \| null | Pre-rendered intro message text (Markdown) |
| `intro_sent_at` | ISO datetime \| null | When the intro was sent |
| `intro_platform` | string \| null | Platform the intro was sent on |
| `created_at` | ISO datetime | When the match was proposed |
| `seeker` | [Post object](#post-object) \| null | The seeker post |
| `camp` | [Post object](#post-object) \| null | The offer-side post (camp or art project) |

---

## Post Object

Embedded in match responses. Key fields:

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Post ID |
| `platform` | string | `reddit` / `discord` / `facebook` |
| `author_display_name` | string \| null | Display name shown in intro |
| `source_url` | string \| null | Link to original post |
| `title` | string \| null | Post title |
| `raw_text` | string \| null | Full post body |
| `status` | string | Post status |
| `role` | string | `seeker` or `camp` (`camp` currently means offer side, including camp/art project) |
| `seeker_intent` | string \| null | `join_art_project`, `join_camp`, `skills_learning`, or `unknown` |
| `vibes` | string[] | Normalized vibe tags |
| `contribution_types` | string[] | Normalized contribution tags |
| `camp_name` | string \| null | Camp or project name if known |
| `post_type` | string | `mentorship` or `infrastructure` |
| `infra_role` | string \| null | `seeking` or `offering` (infra only) |
| `infra_categories` | string[] | Gear/infra categories |

---

## Suggested UI Flow

1. **Queue view** — `GET /matches?status=proposed` — show list sorted by score descending (already sorted by server). Display seeker name, camp/project name, score bar, and a truncated intro draft.

2. **Detail view** — `GET /matches/{id}` — show full intro draft (editable in future), both post cards, score breakdown, and action buttons.

3. **Approve** — `POST /matches/{id}/approve` — on success, re-fetch detail (status is now `approved`) and show "Send Intro" button.

4. **Dry-run preview** — `POST /matches/{id}/send-intro?dry_run=true` — render the intro text in a modal before committing.

5. **Send** — `POST /matches/{id}/send-intro` — on success, status becomes `intro_sent`; show confirmation.

6. **Decline** — `POST /matches/{id}/decline` with optional reason — available from both `proposed` and `approved` states.
