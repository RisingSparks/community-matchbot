# Plan: Add Technical Requirements to Moderator UI Spec

## Context

`docs/MODERATOR_UI_SPEC_v2.md` has solid product/UX requirements but no
technical architecture. The task is to extend it with a new Technical
Requirements section covering: API design, auth, frontend stack, data
contracts, file structure, CORS, and testing approach.

User decisions:
- Auth: **shared password** (MOD_PASSWORD env var + signed cookie)
- Frontend: **separate repo** (deployed independently; CORS required)

---

## What to add to the spec

Append a `## Technical Requirements` section to
`docs/MODERATOR_UI_SPEC_v2.md` with the following subsections:

---

### Backend: New module `src/matchbot/mod/`

Three new files alongside existing `forms/` and `listeners/`:

| File | Purpose |
|------|---------|
| `src/matchbot/mod/router.py` | All `/api/mod/*` FastAPI routes |
| `src/matchbot/mod/schemas.py` | Pydantic request/response models |
| `src/matchbot/mod/auth.py` | Password verification + cookie dependency |

The router is mounted in `server.py` via `create_app()` — no structural
changes to the existing server factory.

Helper logic currently in `cli/cmd_posts.py` (`_apply_field_overrides`,
`_write_event`) must be extracted to a shared module (e.g.
`src/matchbot/mod/actions.py` or `src/matchbot/lifecycle/posts.py`) so both
the CLI and the API can call it without importing from each other.

---

### API endpoints

All endpoints under `/api/mod/`. Auth cookie required on all except
`/api/mod/auth/login`.

**Queue & posts:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/mod/queue` | NEEDS_REVIEW posts, oldest first. Params: `post_type`, `platform`, `limit` (default 50) |
| `GET` | `/api/mod/posts/{id}` | Full post detail + event history |
| `POST` | `/api/mod/posts/{id}/approve` | Approve with optional field overrides |
| `POST` | `/api/mod/posts/{id}/dismiss` | Dismiss with required reason |
| `POST` | `/api/mod/posts/{id}/edit` | Correct fields, stay in NEEDS_REVIEW |
| `POST` | `/api/mod/posts/{id}/re-extract` | Trigger LLM re-extraction (fire-and-forget) |

**Supporting:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/mod/stats` | Queue count, oldest post age in hours, approved/dismissed today |
| `GET` | `/api/mod/taxonomy` | Valid values for all chip pickers |

**Auth:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/mod/auth/login` | Verify password, set HttpOnly cookie |
| `POST` | `/api/mod/auth/logout` | Clear cookie |

---

### Key response shapes (`schemas.py`)

```python
# GET /api/mod/queue → list[QueueItem]
QueueItem:
  id, platform, post_type, role, title
  detected_at, age_hours
  extraction_confidence, extraction_method

# GET /api/mod/posts/{id} → PostDetail
PostDetail:
  # all Post fields
  events: list[EventRecord]  # audit trail

# POST /api/mod/posts/{id}/approve
ApproveRequest:
  note: str | None
  role, vibes, contribution_types, camp_name, year    # optional field overrides
  infra_role, infra_categories, quantity, condition   # optional

# POST /api/mod/posts/{id}/dismiss
DismissRequest:
  reason: str   # required: spam|off-topic|duplicate|not-real|other
  note: str | None

# GET /api/mod/taxonomy → TaxonomyResponse
TaxonomyResponse:
  vibes: list[str]
  contribution_types: list[str]
  infra_categories: list[str]
  conditions: list[str]
  roles: list[str]   # seeker|camp|unknown

# GET /api/mod/stats → QueueStats
QueueStats:
  needs_review_count: int
  oldest_post_age_hours: float | None
  approved_today: int
  dismissed_today: int
```

---

### Auth implementation (`auth.py`)

- New setting: `mod_password: str` in `Settings` (existing Pydantic BaseSettings)
- Login: POST `{password: str}`, constant-time compare against
  `settings.mod_password`, set `HttpOnly; SameSite=Strict` cookie
- Token: HMAC-SHA256 of `{timestamp}` signed with `mod_password` as the key.
  No JWT library — use stdlib `hmac` + `hashlib`. Expiry: 7 days.
- FastAPI dependency `require_mod_auth`: reads cookie, validates HMAC +
  expiry. Returns 401 if invalid. Applied to all `/api/mod/*` routes except
  login.
- No user identity / multi-user support in v1 — actor written to Event
  records as `"moderator"` (not per-person).

---

### CORS

Since the frontend is a separate repo/deployment, CORS is required.

- New setting: `mod_ui_origin: str` (e.g. `https://mod.example.com` or
  `http://localhost:5173` for dev)
- `CORSMiddleware` added in `create_app()` scoped to `/api/mod/*` with:
  - `allow_origins=[settings.mod_ui_origin]`
  - `allow_credentials=True` (required for cookie auth)
  - `allow_methods=["GET", "POST"]`

---

### Frontend stack (separate repo)

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Framework | React + Vite | Lightweight, fast DX, no SSR needed |
| Styling | Tailwind CSS | Fast utility-first, good mobile DX |
| Data fetching | TanStack Query | Request caching, optimistic updates, background refetch |
| PWA | vite-plugin-pwa | Manifest + service worker, home-screen install |
| Routing | React Router v6 | Simple, client-side only |

No component library — custom components for chip pickers, bottom sheet, and
card triage UI to match community-native aesthetic.

**Dev setup:** Vite dev server proxies `/api/` to the FastAPI server (avoids
CORS in development, cookie `SameSite` issues).

---

### Testing

New file: `tests/test_mod_api.py`

- Uses `httpx.AsyncClient` against `create_app(enable_scheduler=False)`
- Reuses `db_session`, `seeker_post_factory`, `camp_post_factory` from
  `tests/conftest.py`
- Auth: test helper that POSTs to `/api/mod/auth/login` and returns a client
  with cookie set
- Covers: queue list, post detail, approve (with + without field overrides),
  dismiss, edit, taxonomy endpoint, stats endpoint, auth rejection on missing
  cookie

---

### Dependency changes

Backend: **no new dependencies** — auth uses stdlib `hmac`/`hashlib`,
CORS uses `fastapi.middleware.cors` (already bundled with FastAPI).

Frontend (separate repo): `react`, `react-dom`, `@tanstack/react-query`,
`tailwindcss`, `vite`, `vite-plugin-pwa`.

---

## Files to modify

1. **`docs/MODERATOR_UI_SPEC_v2.md`** — append Technical Requirements section
   (the actual deliverable of this plan)
2. Nothing else — this is a spec update, not an implementation
