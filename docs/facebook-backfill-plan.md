# Facebook Groups Backfill — Plan

## Context and Goals

The bot currently has a live Facebook webhook in `src/matchbot/listeners/facebook.py` that receives new posts via the Facebook Graph API. This requires a Facebook App with Group Feed permissions, which is difficult to get from Meta. The user wants to also ingest **historical posts** from Facebook Groups to seed the matching system.

The user's primary concern is **account safety** — they do not want Facebook to detect automated activity and ban their account. This shapes every approach decision.

There are two separate problems to solve:
1. **Historical backfill**: Ingest posts that already exist in the group
2. **Ongoing ingestion**: Keep ingesting new posts going forward

This plan focuses on #1. The live webhook may or may not be functional (Meta's Group Feed permissions are hard to get) — that's a separate discussion.

---

## Why Facebook is Harder Than Reddit

Reddit's JSON API (`/r/BurningMan/new.json`) is a documented, public, rate-limited API. Facebook has no equivalent. Facebook Group posts require authentication, and Facebook aggressively fights scrapers. The existing webhook only receives push events going forward — there's no historical API endpoint.

Options for getting historical Facebook posts all involve either:
- **Interacting with Facebook as a logged-in user** (browser-based, ban risk)
- **Accepting data capture during normal manual browsing** (safe, but requires manual work)
- **Official API** (requires Meta app review, limited data)

---

## Full Approach Analysis

### Approach A: Custom Chrome Extension (Passive Fetch Interceptor)
**Recommended primary approach**

A Chrome extension with a content script that patches `window.fetch` (and `XMLHttpRequest`) before Facebook's code loads. As the user naturally scrolls the group, Facebook's infinite-scroll logic fires requests to `/api/graphql/`. The extension intercepts the response bodies and accumulates them. When done, the user clicks "Download" to save a JSON file, which the Python script processes.

**Why this is safe:**
- Zero synthetic events. All user activity (scrolling, clicking) generates real `isTrusted: true` events
- The extension is passive — it observes, never initiates
- Facebook cannot distinguish this from any other extension a user has installed (uBlock Origin, LastPass, etc. all patch fetch/XHR constantly)
- The bot's scripts never make a single network request to Facebook

**Why this is better than HAR:**
- HAR files contain your entire browser session's cookies, auth tokens, and traffic from all sites — security risk if ever mishandled
- HAR files are huge (100MB+ for a typical session) because they capture every asset (images, fonts, CSS)
- The extension captures ONLY the GraphQL responses containing post data — a compact, targeted JSON file
- No DevTools setup required each time (just scroll naturally, click Download)
- Reusable: build once, use for every future backfill season

**Technical challenges and solutions:**

**1. MV3 Service Worker Lifetime**
In Chrome Manifest V3, service workers are not persistent — Chrome terminates them after ~30 seconds of inactivity. This is a real problem for a long scrolling session.

*Solution*: Store captured data in `chrome.storage.session` instead of in-memory. `chrome.storage.session` persists for the browser session even if the service worker is killed and restarted. Each GraphQL response is appended to the session storage array immediately when received.

**2. MAIN world vs ISOLATED world communication**
Content scripts in MV3 run in an ISOLATED world by default and cannot access or patch the page's `window.fetch`. To patch the page's actual `window.fetch`, we need `"world": "MAIN"` in the content script config. But MAIN world scripts cannot use `chrome.runtime.sendMessage` (the Chrome extension API is not available in MAIN world).

*Solution*: Two-script architecture:
- `content_main.js` runs in MAIN world: patches `window.fetch`/`XHR`, broadcasts captured data via `document.dispatchEvent(new CustomEvent('fb_graphql_captured', {detail: responseText}))`
- `content_relay.js` runs in ISOLATED world: listens for the custom event and calls `chrome.storage.session.get/set` to append the data

**3. XHR alongside Fetch**
Facebook may use `XMLHttpRequest` for some requests, not just `fetch`. Both need to be patched in `content_main.js`.

**4. Streaming / compressed responses**
Facebook gzips most responses. Chrome automatically decompresses before handing the response to the page's JavaScript, so `response.text()` returns decoded JSON. No special handling needed at the extension level.

**5. Filtering noise**
Not all `/api/graphql` requests contain post data. Many are for UI metadata, reaction counts, etc. The extension should capture ALL GraphQL responses — the Python script will filter them during parsing. This keeps the extension simple and avoids brittle URL/payload pattern matching.

**Breakdown risk:**
If Facebook changes how it loads group posts (e.g., switches from GraphQL to a different mechanism), the extension stops collecting data. The Python parser already handles this gracefully (it just won't find post-like nodes). The user would notice because post counts would drop to zero.

**Files:**
```
extensions/fb-group-collector/
  manifest.json
  content_main.js     (~40 lines — patches window.fetch + XHR)
  content_relay.js    (~30 lines — relays captured data to storage)
  background.js       (~40 lines — service worker, handles download request)
  popup.html          (~20 lines)
  popup.js            (~30 lines — start/stop/download UI)
```

**Installation**: Chrome Settings → Extensions → Developer Mode → Load Unpacked → select the `extensions/fb-group-collector/` directory. Must be on a Chromium-based browser. No publishing to Chrome Web Store needed for personal use.

---

### Approach B: HAR File Export
**Recommended fallback / simpler first step**

User opens Chrome DevTools Network tab ("Preserve log" checked), navigates to the Facebook Group, scrolls to load desired posts, exports the entire session as a HAR file via right-click → "Save all as HAR with content". Python script parses the HAR.

**Tradeoffs vs Extension:**
- ✅ Simpler to implement (no extension build)
- ✅ Good for a first pass or one-off capture
- ❌ HAR files contain session cookies and all browser traffic — **security risk**: must never be committed to git, stored carefully
- ❌ Very large files (100MB+) — all browser resources included, not just GraphQL
- ❌ Requires DevTools setup before browsing starts; if you forget and browse first, you miss those responses
- ❌ Need to do the export ceremony every time; can't just "scroll and go"
- Same Python parser logic as extension approach

**HAR format details:**
```json
{
  "log": {
    "entries": [
      {
        "request": {"url": "https://www.facebook.com/api/graphql/", ...},
        "response": {
          "content": {
            "text": "...",          // response body
            "encoding": "base64"   // present if binary/compressed
          }
        }
      }
    ]
  }
}
```
Filter entries where request URL contains `/api/graphql`. Decode base64 if `encoding == "base64"`. Split by `\n` and attempt to parse each line as JSON (JSONL format).

---

### Approach C: Browser Automation (Playwright)
**Not recommended**

Even with "connect to existing Chrome" mode (`--remote-debugging-port`), Playwright automation is still detectable:

- **`isTrusted: false`** on all synthetic events (scrolls, clicks). Facebook checks this.
- **CDP overhead**: Chrome DevTools Protocol is used by Playwright; some anti-bot systems detect the CDP connection itself.
- **Behavioral signals**: Programmatic scrolling is too regular. Even with randomized delays, the distribution is different from human scrolling.
- **JavaScript artifacts**: Some automation libraries leave traces in the JS environment even when using a real Chrome instance.

The risk-reward ratio is poor given the user's concerns. Don't implement.

---

### Approach D: Claude Chrome MCP Plugin
**Potentially useful for one-off small captures only**

The Claude in Chrome extension runs inside the user's real browser profile, avoiding most fingerprinting concerns. However:

- `mcp__Claude_in_Chrome__javascript_tool` executes JS that produces `isTrusted: false` events for any interactions
- `mcp__Claude_in_Chrome__get_page_text` reads the visible DOM text — undetectable but loses structured data (no author IDs, post IDs, timestamps)
- Facebook's DOM is heavily obfuscated (class names like `x78zum5 xdt5ytf`) — parsing it is fragile
- User said it "feels a little buggy"
- Requires Claude's attention throughout the entire capture session
- Context limits for large groups

**Only scenario where this makes sense**: User has already manually scrolled a Facebook group page and wants Claude to read and extract the currently-visible posts interactively, without any scrolling automation. Good for a handful of posts, not for bulk backfill.

---

### Approach E: Facebook Graph API (Official)
**Not viable for this use case**

Facebook's Groups API requires:
- Creating a Facebook App
- Getting approved for `groups_access_member_info` and `user_managed_groups` permissions (requires Meta app review for sensitive permissions)
- The app must be installed by a group admin

Meta severely restricted Group API access after Cambridge Analytica. Getting these permissions for a third-party bot is effectively impossible without a commercial justification. The existing webhook already uses this path for live events — the historical data API simply doesn't exist.

---

## Recommended Implementation Plan

### Phase 1: HAR-based backfill (implement first)

Do this first because:
- Lower build effort — get unblocked immediately
- No extension development needed
- Validates the Python parsing logic before building the extension
- User can capture a real HAR file to test against

**Python files:**

**`src/matchbot/listeners/facebook_har.py`** — shared parsing + ingestion logic

Core parsing strategy:
```python
def _find_post_nodes(obj: Any, depth: int = 0) -> list[dict]:
    """Recursively walk a JSON object, return dicts that look like Facebook posts."""
    # Stops recursing when a post-like node is found (posts don't contain other posts)
    # Depth limit of ~20 prevents stack overflow on deeply nested structures
```

What "looks like a Facebook post":
- Has text content: `message.text` (dict with "text" key), or `message` as a string, or `body.text`
- Has a timestamp: `creation_time` or `created_time` (Unix integer)
- Has an ID: `id` or `post_id` (non-empty string)
- Has actor/author info: `actors[0].id/name` or `from.id/name`

Why recursive search instead of hard-coded key paths: Facebook changes their GraphQL response structure with every product update. A recursive search based on semantic field presence is far more stable than navigating specific paths like `data.node.group_feed.edges[0].node.story`.

Field extraction supports two shapes (matching existing `facebook.py` webhook patterns):
- **GraphQL relay style**: `message.text`, `actors[0].id`, `actors[0].name`, `creation_time`, `id`, `url`
- **Webhook flat style** (matches `_handle_feed_change` in `facebook.py`): `message` (string), `from.id`, `from.name`, `created_time`, `post_id`, `permalink_url`

**Known parsing complications:**
- Photo-only posts have no `message.text` → correctly filtered out (can't match without text)
- Link share posts: `message.text` is the author's caption; there may also be a `title` and `description` from the linked article. Prefer `message.text` as the raw_text. Good.
- Video posts with captions: same as above — use `message.text`
- Relay post IDs are sometimes prefixed like `post:12345` or are `pfbid...` format. Strip the `post:` prefix if present.
- JSONL responses: split on `\n`, parse each line independently, swallow parse errors for non-JSON lines

**HAR parsing entry point**: `parse_har_file(path: Path) -> list[dict]`
- Load HAR JSON
- Filter entries by URL containing `/api/graphql`
- Decode base64-encoded bodies
- For each response body: split on `\n`, parse each line, call `_find_post_nodes`
- Deduplicate by `platform_post_id` across all entries
- Return list of field dicts

**Ingestion loop**: `backfill_facebook_posts(post_fields_list, *, group_name, since_datetime, dry_run, sleep_seconds, no_extract) -> dict[str, int]`
- Mirrors `reddit_json.py` ingestion pattern exactly
- `since_datetime` filter applied before DB lookup
- DB dedup: `select(Post.id).where(platform==FACEBOOK, platform_post_id==...)`
- Create `Post(status=RAW, platform=FACEBOOK, ...)`
- Call `process_post(..., on_extraction_error="raw")`
- `asyncio.sleep(sleep_seconds)` between LLM calls (throttles LLM provider, NOT Facebook)
- Returns: `files, parsed, new_candidates, deduped, before_cutoff, matched, skipped, extracted, raw_after_error`

**`scripts/backfill_facebook.py`** — Typer CLI, mirrors `scripts/backfill_reddit_json.py`

Auto-detects input format:
- If file parses as JSON with `log.entries` key → HAR format
- Otherwise → extension JSON format (array of response text strings)
```bash
uv run python scripts/backfill_facebook.py data/raw/session.har \
  --group-name "Burning Man Community" \
  --since-date 2025-01-01 \
  [--dry-run] [--no-extract] [--sleep-seconds 0.5] [--reset-db]
```

**`.gitignore`** — add before anything else:
```
# HAR files contain session cookies — never commit
*.har
data/raw/
```

---

### Phase 2: Chrome Extension (build after validating Phase 1)

Build after the Python parsing pipeline works and has been tested against a real HAR file.

**`extensions/fb-group-collector/manifest.json`**:
```json
{
  "manifest_version": 3,
  "name": "FB Group Post Collector",
  "version": "1.0",
  "description": "Captures Facebook Group GraphQL responses for Burning Man matchbot",
  "permissions": ["storage"],
  "content_scripts": [
    {
      "matches": ["*://*.facebook.com/*"],
      "js": ["content_main.js"],
      "run_at": "document_start",
      "world": "MAIN"
    },
    {
      "matches": ["*://*.facebook.com/*"],
      "js": ["content_relay.js"],
      "run_at": "document_start",
      "world": "ISOLATED"
    }
  ],
  "background": {"service_worker": "background.js"},
  "action": {"default_popup": "popup.html"}
}
```

**`content_main.js`** — Patches `window.fetch` and `XMLHttpRequest`:
```js
// Runs in MAIN world — can access and patch page's fetch/XHR
// Broadcasts captured responses via CustomEvent (MAIN→ISOLATED bridge)

const origFetch = window.fetch;
window.fetch = async function(...args) {
  const response = await origFetch.apply(this, args);
  const url = (typeof args[0] === 'string' ? args[0] : args[0]?.url) ?? '';
  if (url.includes('/api/graphql')) {
    response.clone().text().then(text => {
      document.dispatchEvent(new CustomEvent('_fbgc', {detail: text}));
    }).catch(() => {});
  }
  return response;
};

// Also patch XHR
const OrigXHR = window.XMLHttpRequest;
// ... (open + send intercept to capture response text for /api/graphql URLs)
```

**`content_relay.js`** — Relays from page to extension storage:
```js
// Runs in ISOLATED world — can use chrome.storage API
// Listens for CustomEvents dispatched by content_main.js

document.addEventListener('_fbgc', async (e) => {
  const result = await chrome.storage.session.get(['fbgc_responses', 'fbgc_capturing']);
  if (!result.fbgc_capturing) return;
  const existing = result.fbgc_responses ?? [];
  existing.push(e.detail);
  await chrome.storage.session.set({fbgc_responses: existing});
});
```

**`background.js`** — Service worker, handles popup actions:
```js
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'get_state') {
    chrome.storage.session.get(['fbgc_capturing', 'fbgc_responses'], (r) => {
      sendResponse({capturing: !!r.fbgc_capturing, count: (r.fbgc_responses ?? []).length});
    });
    return true; // async response
  }
  if (msg.type === 'set_capturing') {
    chrome.storage.session.set({fbgc_capturing: msg.value});
  }
  if (msg.type === 'download') {
    chrome.storage.session.get('fbgc_responses', (r) => {
      sendResponse({data: r.fbgc_responses ?? []});
    });
    return true;
  }
  if (msg.type === 'clear') {
    chrome.storage.session.set({fbgc_responses: []});
  }
});
```

**`popup.html/popup.js`** — Simple UI:
- Shows current state: "Capturing: ON/OFF" and "X responses captured"
- Toggle button for start/stop
- "Download fb_posts.json" button that triggers background download action
- "Clear" button

**Extension output format**: `fb_posts.json` is an array of raw GraphQL response text strings — exactly what the Python parser expects for the "extension JSON" input format. One element per HTTP response body. The Python parser already handles both HAR and extension formats via auto-detection.

---

## Python Parser Robustness Strategy

Facebook's response structure changes. The parser must not break. Strategy:

1. **Catch everything**: Wrap `_find_post_nodes` in a try/except; log failures at DEBUG level and continue
2. **Prefer, don't require**: `parse_facebook_post_fields` returns `None` if the minimum viable fields (text + some ID) are absent. Partial data is dropped rather than crashing.
3. **Multiple shapes**: The field extractor tries multiple key path patterns for each field (see MAIN vs ISOLATED shapes above)
4. **Deduplication is defensive**: If two response blobs contain the same post, deduplication handles it gracefully
5. **Log unmatched responses**: In verbose mode, log response blobs where zero posts were found — helps diagnose when Facebook changes their format

---

## Data Quality Concerns

Not all Facebook Group posts will be useful for matching:

- **Photo-only posts**: `message.text` is absent → filtered out. Correct behavior.
- **Link share posts without author text**: `message.text` is empty, only linked article title present → filtered out. Correct behavior — can't match without the person's actual description.
- **Link share posts WITH author text**: `message.text` contains the author's caption → extracted correctly.
- **Event posts**: May have a different structure. The keyword filter in `process_post()` will likely mark them as `SKIPPED`. Fine.
- **Admin posts / pinned announcements**: Will be processed and likely skipped by keyword filter. Fine.
- **Reshares**: May have the original post's text, not a new seeker post. Likely skipped by keyword filter. Fine.

The existing `process_post()` pipeline handles content filtering via the keyword filter — we don't need to add special cases in the Facebook parser.

---

## Security Considerations

**HAR files**: Contain `Cookie`, `Authorization`, and `X-FB-*` headers from your Facebook session. Never commit to git. Store in `data/raw/` (add to `.gitignore`). Delete after use or store in a location outside the repo.

**Extension output files**: Contain only GraphQL response bodies — no cookies or auth headers. Still contains Facebook user IDs and names, which are PII. Treat as sensitive data but lower risk than HAR.

**Both**: If you store these files on a shared machine or cloud storage, others could potentially use the session tokens in HAR files to hijack your Facebook session.

---

## Testing Strategy

**`tests/test_facebook_har.py`**:

1. `test_find_post_nodes_graphql_relay_style` — nested `data.node.group_feed.edges` structure, assert post found
2. `test_find_post_nodes_flat` — flat webhook-style dict, assert post found
3. `test_find_post_nodes_depth_limit` — deeply nested dict (> 20 levels), assert no crash
4. `test_find_post_nodes_no_false_positives` — dict with `id` and `creation_time` but no text, assert `[]`
5. `test_parse_facebook_post_fields_graphql` — relay style, assert all fields extracted correctly
6. `test_parse_facebook_post_fields_webhook` — flat style, assert fields match `facebook.py` webhook extraction
7. `test_parse_facebook_post_fields_link_share` — dict with `message.text` (author caption) + `title` (article), assert `raw_text` uses author caption
8. `test_parse_facebook_post_fields_no_text_returns_none`
9. `test_parse_facebook_post_fields_no_id_returns_none`
10. `test_jsonl_parsing` — multi-line response text, one post per line, assert both parsed
11. `test_backfill_deduplication` — use `db_session` fixture, insert a Post, run backfill with same post_id, assert `deduped` count = 1, no duplicate created
12. `test_backfill_since_date_filter` — post with old timestamp should be `before_cutoff`, not inserted
13. `test_backfill_dry_run` — assert no DB writes with `dry_run=True`

Use `tmp_path` pytest fixture to create temporary HAR/JSON files for file-based tests.

---

## File Summary

| File | Action | Notes |
|---|---|---|
| `.gitignore` | Modify | Add `*.har` and `data/raw/` |
| `src/matchbot/listeners/facebook_har.py` | Create | HAR + extension JSON parsing, ingestion loop |
| `scripts/backfill_facebook.py` | Create | Typer CLI, auto-detects input format |
| `tests/test_facebook_har.py` | Create | 13 tests |
| `extensions/fb-group-collector/` | Create (Phase 2) | 6 files, ~200 lines JS total |
| `src/matchbot/listeners/facebook.py` | Do NOT modify | Working as-is; optional future refactor to share field extractor |

---

## Live Ingestion Note

The existing webhook in `facebook.py` requires:
1. A Facebook App with `groups:read` and Group Feed webhook subscription permissions
2. Meta App Review approval for those permissions (non-trivial for a third-party bot)
3. The app installed on the specific Facebook Group

If this isn't set up and working, a practical alternative for "live" ingestion is running the extension capture **weekly** — scroll through new posts since the last capture, download, run the script. Less automated but completely safe and doesn't require Meta approval.

---

## Implementation Order

1. **Add `*.har` to `.gitignore`** — first, safety
2. **Create `src/matchbot/listeners/facebook_har.py`** — parser + ingestion logic
3. **Create `scripts/backfill_facebook.py`** — Typer CLI
4. **Create `tests/test_facebook_har.py`** — validate parser before using against real data
5. **Run tests** and capture a real HAR from Facebook to smoke test
6. **Build Chrome extension** (`extensions/fb-group-collector/`) — after Python side is proven

---

## Verification

```bash
# Step 1: Unit tests pass
uv run pytest tests/test_facebook_har.py -x -q

# Step 2: Dry run against a real HAR file
uv run python scripts/backfill_facebook.py data/raw/session.har \
  --group-name "BM Community" --dry-run

# Step 3: Real run, no LLM (verify posts land in DB without extraction cost)
uv run python scripts/backfill_facebook.py data/raw/session.har \
  --group-name "BM Community" --no-extract

# Step 4: Inspect what landed
uv run matchbot posts list

# Step 5: Full run with LLM
uv run python scripts/backfill_facebook.py data/raw/session.har \
  --group-name "BM Community" --sleep-seconds 1.0

# Step 6: Verify deduplication — re-running same file should add 0 new posts
uv run python scripts/backfill_facebook.py data/raw/session.har \
  --group-name "BM Community" --dry-run
# Expect: new_candidates=0, deduped=N
```
