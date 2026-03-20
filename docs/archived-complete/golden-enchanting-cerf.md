# Plan: Implement Moderator API (`/api/mod/`)

## Context

The mod API spec in `docs/MOD_API_REFERENCE.md` defines 10 endpoints for a human moderator to review, approve, dismiss, and edit incoming posts. None of these routes exist yet — the FastAPI server only mounts the Facebook webhook and intake forms routers. All the underlying business logic (status transitions, matching, taxonomy) already exists in the CLI layer and needs to be surfaced as an HTTP API.

---

## Files to Create

- `src/matchbot/mod/__init__.py` — empty package marker
- `src/matchbot/mod/router.py` — all 10 endpoints + auth dependency
- `tests/test_mod_api.py` — async tests via httpx + dependency overrides

## Files to Modify

- `src/matchbot/settings.py` — add `mod_password` and `mod_secret_key`
- `src/matchbot/server.py` — mount the mod router

---

## Step 1: Settings (`src/matchbot/settings.py`)

Add two fields under the `# Moderator` section:

```python
mod_password: str = Field(default="", description="Password for /api/mod auth")
mod_secret_key: str = Field(default="", description="HMAC secret for mod_session cookie")
```

Empty defaults → auth is a no-op check only when set (still validate cookie if secret_key is non-empty).

---

## Step 2: Mod Router (`src/matchbot/mod/router.py`)

### Session dependency (same pattern as `forms/router.py`)

```python
async def _get_session():
    from matchbot.db.engine import get_engine
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        yield session
```

### Auth dependency

Cookie format: `{timestamp_ms}.{hmac_sha256_hex}` where HMAC is `HMAC(mod_secret_key, timestamp_ms_str)`.

```python
def _require_mod(request: Request) -> None:
    settings = get_settings()
    if not settings.mod_secret_key:
        return  # auth disabled in dev
    cookie = request.cookies.get("mod_session")
    if not cookie or "." not in cookie:
        raise HTTPException(401, "Not authenticated")
    ts_str, sig = cookie.rsplit(".", 1)
    try:
        ts_ms = int(ts_str)
    except ValueError:
        raise HTTPException(401, "Invalid session")
    now_ms = int(time.time() * 1000)
    if now_ms - ts_ms > 7 * 24 * 3600 * 1000:
        raise HTTPException(401, "Session expired")
    expected = hmac.new(settings.mod_secret_key.encode(), ts_str.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(401, "Invalid session")
```

### Request/response Pydantic models (defined in `router.py`)

```python
class LoginRequest(BaseModel):
    password: str

class OverrideFields(BaseModel):
    note: str | None = None
    role: str | None = None
    vibes: list[str] | None = None
    contribution_types: list[str] | None = None
    camp_name: str | None = None
    year: int | None = None
    infra_role: str | None = None
    infra_categories: list[str] | None = None
    quantity: str | None = None
    condition: str | None = None

DISMISS_REASONS = {"spam", "off-topic", "duplicate", "not-real", "other"}

class DismissRequest(BaseModel):
    reason: str
    note: str | None = None
    @field_validator("reason")
    @classmethod
    def check_reason(cls, v):
        if v not in DISMISS_REASONS:
            raise ValueError(f"must be one of {sorted(DISMISS_REASONS)}")
        return v
```

### Field override helper (API-native, not reusing CLI version which uses `rprint`)

```python
def _apply_mod_overrides(post: Post, body: OverrideFields) -> None:
    """Apply list-valued overrides to post; multi-value fields normalized via taxonomy."""
    if body.role is not None:
        post.role = body.role
    if body.vibes is not None:
        post.vibes = "|".join(normalize_vibes(body.vibes))
    if body.contribution_types is not None:
        post.contribution_types = "|".join(normalize_contribution_types(body.contribution_types))
    if body.camp_name is not None:
        post.camp_name = body.camp_name
    if body.year is not None:
        post.year = body.year
    if body.infra_role is not None:
        post.infra_role = body.infra_role
    if body.infra_categories is not None:
        post.infra_categories = "|".join(normalize_infra_categories(body.infra_categories))
    if body.quantity is not None:
        post.quantity = body.quantity
    if body.condition is not None:
        post.condition = body.condition
```

### Event helper (matches pattern in `cmd_posts.py:_write_event`)

```python
async def _write_event(session, post, event_type, payload, note=None):
    event = Event(
        event_type=event_type,
        post_id=post.id,
        actor="moderator",
        payload=json.dumps(payload),
        note=note,
    )
    session.add(event)
```

### All 10 endpoints

**`POST /auth/login`** — no auth required
Compare `body.password` to `settings.mod_password` with `hmac.compare_digest`. Set `mod_session` cookie (HttpOnly, SameSite=Strict, Path=/api/mod, Max-Age=604800).

**`POST /auth/logout`** — requires auth
Set cookie with Max-Age=0.

**`GET /queue`** — requires auth
Query Posts with status=NEEDS_REVIEW, filter by optional `post_type`/`platform` query params, order by `detected_at` asc, limit (default 50). Compute `age_hours = round((now - post.detected_at).total_seconds() / 3600, 1)`.

**`GET /posts/{id}`** — requires auth
Fetch Post by full UUID or 404. Load related Events via `select(Event).where(Event.post_id == id)`. Return full post with multi-value fields converted to lists (`post.vibes_list()`, etc.) plus events list.

**`POST /posts/{id}/approve`** — requires auth
1. Load post, 409 if not NEEDS_REVIEW.
2. Call `_apply_mod_overrides(post, body)`.
3. Set `post.status = PostStatus.INDEXED`.
4. Write `post_approved` event.
5. Commit.
6. Trigger `propose_matches(session, post)`.
Return `{"ok": True, "post_id": post.id, "new_status": "INDEXED"}`.

**`POST /posts/{id}/dismiss`** — requires auth
1. Load post, 409 if not in {NEEDS_REVIEW, ERROR}.
2. Set `post.status = PostStatus.SKIPPED`.
3. Write `post_dismissed` event with reason.
4. Commit.
Return `{"ok": True, "post_id": post.id, "new_status": "SKIPPED"}`.

**`POST /posts/{id}/edit`** — requires auth
1. Load post, 409 if not NEEDS_REVIEW.
2. Validate at least one non-null override field (422 if all null).
3. Call `_apply_mod_overrides(post, body)`.
4. Write `post_edited` event.
5. Commit.
Return `{"ok": True, "post_id": post.id}`.

**`POST /posts/{id}/re-extract`** — requires auth
1. Load post, 404 if not found.
2. Enqueue background task: reset post to RAW, commit, run `process_post()` in a fresh session via `get_session()` context manager (so it runs after response).
3. Return `{"ok": True, "post_id": post.id, "message": "re-extraction queued"}`.
Use FastAPI `BackgroundTasks` to fire-and-forget.

**`GET /taxonomy`** — requires auth
Return `{vibes: sorted(VIBES), contribution_types: sorted(CONTRIBUTION_TYPES), infra_categories: sorted(INFRASTRUCTURE_CATEGORIES), conditions: sorted(INFRASTRUCTURE_CONDITIONS), roles: ["seeker", "camp", "unknown"]}`.

**`GET /stats`** — requires auth
Four separate DB queries:
- count of Posts with status=NEEDS_REVIEW
- max detected_at among NEEDS_REVIEW posts (compute age_hours from it)
- count of Events with event_type="post_approved" and occurred_at >= today (UTC midnight)
- count of Events with event_type="post_dismissed" and occurred_at >= today

---

## Step 3: Mount in `src/matchbot/server.py`

```python
from matchbot.mod.router import router as mod_router
app.include_router(mod_router)
```

Router uses `prefix="/api/mod"`, `tags=["mod"]`.

---

## Step 4: Tests (`tests/test_mod_api.py`)

Use `httpx.AsyncClient` with `ASGITransport` + `db_session` fixture + dependency overrides:

```python
@pytest.fixture
async def mod_client(db_session):
    from httpx import AsyncClient, ASGITransport
    from matchbot.mod.router import _get_session, _require_mod
    app = create_app(enable_scheduler=False)
    async def override_session():
        yield db_session
    app.dependency_overrides[_get_session] = override_session
    app.dependency_overrides[_require_mod] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
```

Test cases:
1. `test_login_valid` — valid password → 200 + sets cookie
2. `test_login_invalid` — wrong password → 401
3. `test_queue_empty` — no posts → `[]`
4. `test_queue_returns_needs_review` — NEEDS_REVIEW post appears; INDEXED post does not
5. `test_queue_filter_by_platform` — platform filter works
6. `test_post_detail_404` — unknown ID → 404
7. `test_post_detail_returns_events` — post + events in response
8. `test_approve_transitions_to_indexed` — post status becomes INDEXED
9. `test_approve_409_wrong_status` — INDEXED post → 409
10. `test_dismiss_requires_reason` — missing reason → 422
11. `test_dismiss_transitions_to_skipped`
12. `test_edit_stays_needs_review`
13. `test_edit_requires_at_least_one_field` — all-null body → 422
14. `test_taxonomy_keys_present` — response has vibes/contribution_types/infra_categories/conditions/roles
15. `test_stats_counts` — create NEEDS_REVIEW post, check needs_review_count=1

---

## Known Discrepancies from Spec

| Spec | Implementation | Reason |
|------|----------------|--------|
| `"id": 42` (integer) | UUID string | Model uses `uuid4()` PKs |
| `"created_at"` in events | `"occurred_at"` | Actual Event model field name |
| `"extraction_method": "llm"` | Full value e.g. `"llm_anthropic"` | Real extraction method strings |

---

## Verification

```bash
# Run unit tests
uv run pytest tests/test_mod_api.py -x -q

# Run all tests to check nothing broken
uv run pytest tests/ -x -q

# Manual smoke test (with server running)
curl -s -X POST http://localhost:8080/api/mod/auth/login \
  -H 'Content-Type: application/json' -d '{"password":"..."}' -c cookies.txt
curl -s http://localhost:8080/api/mod/queue -b cookies.txt | python -m json.tool
curl -s http://localhost:8080/api/mod/taxonomy -b cookies.txt | python -m json.tool
curl -s http://localhost:8080/api/mod/stats -b cookies.txt | python -m json.tool
```
