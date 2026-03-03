# Moderator API Reference

All endpoints are under `/api/mod/`. All endpoints except `/api/mod/auth/login`
require a valid `mod_session` cookie (set by login, validated via HMAC-SHA256).

---

## Auth

### `POST /api/mod/auth/login`

No auth cookie required.

**Request**
```json
{ "password": "..." }
```

**Response `200`**
```json
{ "ok": true }
```
Sets cookie: `mod_session=<hmac-token>; HttpOnly; SameSite=Strict; Path=/api/mod`

**Response `401`**
```json
{ "detail": "Invalid password" }
```

---

### `POST /api/mod/auth/logout`

No request body.

**Response `200`**
```json
{ "ok": true }
```
Clears `mod_session` cookie (`Max-Age=0`).

---

## Queue

### `GET /api/mod/queue`

Returns NEEDS_REVIEW posts, oldest first.

**Query params**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `post_type` | `string` | — | Filter: `mentorship` or `infrastructure` |
| `platform` | `string` | — | Filter: `reddit`, `discord`, or `facebook` |
| `limit` | `integer` | `50` | Max posts to return |

**Response `200` — `list[QueueItem]`**
```json
[
  {
    "id": 42,
    "platform": "reddit",
    "post_type": "mentorship",
    "role": "seeker",
    "title": "Looking for a camp or art project that does...",
    "detected_at": "2025-04-10T14:32:00Z",
    "age_hours": 3.5,
    "extraction_confidence": 0.61,
    "extraction_method": "llm"
  }
]
```

---

## Posts

### `GET /api/mod/posts/{id}`

Full post detail including all extracted fields and event history.

**Response `200` — `PostDetail`**
```json
{
  "id": 42,
  "platform": "reddit",
  "post_type": "mentorship",
  "status": "NEEDS_REVIEW",
  "source_url": "https://reddit.com/r/BurningMan/...",
  "raw_text": "Hey everyone, I'm looking for...",

  "role": "seeker",
  "vibes": ["inclusive", "art-focused"],
  "contribution_types": ["sound", "art"],
  "camp_name": null,
  "year": 2025,
  "seeker_intent": "membership",
  "infra_role": null,
  "infra_categories": [],
  "quantity": null,
  "condition": null,
  "extraction_confidence": 0.61,
  "extraction_method": "llm",

  "detected_at": "2025-04-10T14:32:00Z",
  "age_hours": 3.5,

  "events": [
    {
      "id": 1,
      "event_type": "detected",
      "actor": "system",
      "note": null,
      "created_at": "2025-04-10T14:32:00Z"
    }
  ]
}
```

**Response `404`**
```json
{ "detail": "Post not found" }
```

---

### `POST /api/mod/posts/{id}/approve`

Promotes post to `INDEXED` and triggers match proposals. All body fields are
optional — only provided fields are applied as overrides before indexing.

**Request**
```json
{
  "note": "Looks good, fixed vibes",
  "role": null,
  "vibes": ["inclusive", "art-focused"],
  "contribution_types": null,
  "camp_name": null,
  "year": null,
  "infra_role": null,
  "infra_categories": null,
  "quantity": null,
  "condition": null
}
```

**Response `200`**
```json
{ "ok": true, "post_id": 42, "new_status": "INDEXED" }
```

**Response `409`** (post no longer in NEEDS_REVIEW)
```json
{ "detail": "Post is not in NEEDS_REVIEW (current status: INDEXED)" }
```

---

### `POST /api/mod/posts/{id}/dismiss`

Moves post to `SKIPPED`. `reason` is required.

**Request**
```json
{
  "reason": "spam",
  "note": "Clearly a bot post"
}
```

Valid `reason` values: `spam` · `off-topic` · `duplicate` · `not-real` · `other`

**Response `200`**
```json
{ "ok": true, "post_id": 42, "new_status": "SKIPPED" }
```

**Response `422`** (missing or invalid reason)
```json
{ "detail": [{ "loc": ["body", "reason"], "msg": "field required", "type": "value_error.missing" }] }
```

**Response `409`** (post no longer in NEEDS_REVIEW)
```json
{ "detail": "Post is not in NEEDS_REVIEW (current status: SKIPPED)" }
```

---

### `POST /api/mod/posts/{id}/edit`

Applies field corrections; post stays in `NEEDS_REVIEW`. At least one field
must be non-null.

**Request** (same optional fields as approve, no status change)
```json
{
  "role": "camp",
  "vibes": null,
  "contribution_types": ["sound"],
  "camp_name": "Dusty Phoenix",
  "year": null,
  "infra_role": null,
  "infra_categories": null,
  "quantity": null,
  "condition": null,
  "note": "Corrected role and camp/project name"
}
```

**Response `200`**
```json
{ "ok": true, "post_id": 42 }
```

---

### `POST /api/mod/posts/{id}/re-extract`

Triggers LLM re-extraction asynchronously (fire-and-forget). No request body.

**Response `200`**
```json
{ "ok": true, "post_id": 42, "message": "re-extraction queued" }
```

---

## Supporting

### `GET /api/mod/taxonomy`

Returns valid values for all constrained chip-picker fields. Sourced from the
same taxonomy the backend uses — single source of truth.

**Response `200`**
```json
{
  "vibes": ["inclusive", "art-focused", "party", "spiritual", "family-friendly", "..."],
  "contribution_types": ["sound", "art", "build", "food", "..."],
  "infra_categories": ["power", "water", "shade", "vehicles", "..."],
  "conditions": ["new", "good", "fair", "poor"],
  "roles": ["seeker", "camp", "unknown"]
}
```

`role=camp` currently represents the offer side for mentorship matches, including
camp posts and art-project posts. The same applies to `camp_name` (camp or project name).

---

### `GET /api/mod/stats`

Current queue health snapshot.

**Response `200`**
```json
{
  "needs_review_count": 7,
  "oldest_post_age_hours": 31.2,
  "approved_today": 4,
  "dismissed_today": 1
}
```

---

## Error responses

| Status | Meaning |
|--------|---------|
| `401` | Missing, invalid, or expired `mod_session` cookie |
| `404` | Post ID not found |
| `409` | Post is in the wrong status for the requested action |
| `422` | Request body validation failed (FastAPI default) |
| `500` | Unexpected server error |

---

## Cookie details

| Attribute | Value |
|-----------|-------|
| Name | `mod_session` |
| Value | `{timestamp_ms}.{hmac_sha256_hex}` |
| HttpOnly | yes |
| SameSite | Strict |
| Path | `/api/mod` |
| Expiry | 7 days from login |

Token is validated on every request by re-computing HMAC and checking
`timestamp_ms` against current time. No token refresh — re-login after expiry.
