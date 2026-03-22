# Platform Setup Guide

Step-by-step instructions for connecting Reddit, Discord, and Facebook to the matchbot.
Ordered easiest → hardest.

---

## Step 0 — Create your `.env` file

```bash
cp .env.example .env
```

Edit `.env` as you go — the app reads all credentials from this file at startup.

---

## Platform 1: Reddit (~20 min)

Reddit is read-only streaming. No webhook or public server required.

### Stage-1 fallback (no Reddit API app approval)

If Reddit app credentials are unavailable, you can run the unauthenticated JSON poller instead:

```bash
uv run python scripts/run_reddit_json_listener.py
```

This polls `https://www.reddit.com/r/BurningMan/new.json` every 5 minutes by default, applies the keyword pre-filter, and writes posts to the existing `post` table.

### 1. Create a Reddit app

- Go to https://www.reddit.com/prefs/apps
- Click **"create another app"** at the bottom
- Type: **script**
- Name: `matchbot`
- Redirect URI: `http://localhost:8080` (doesn't matter for script type)
- Submit → copy the **client ID** (shown under the app name) and **client secret**

### 2. Fill in `.env`

```
REDDIT_ENABLED=true
REDDIT_CLIENT_ID=abc123
REDDIT_CLIENT_SECRET=xyz456
REDDIT_USER_AGENT=matchbot/0.1 by u/your-reddit-username
REDDIT_USERNAME=your-reddit-username
REDDIT_PASSWORD=your-reddit-password
```

### 3. Configure subreddits

`src/matchbot/config/sources.yaml` is already set with `BurningMan`. Swap in a subreddit you control for initial testing.

### 4. Test the connection

```bash
uv run python -c "
import asyncio, asyncpraw
async def test():
    r = asyncpraw.Reddit(client_id='abc123', client_secret='xyz456',
        user_agent='test', username='user', password='pass')
    me = await r.user.me()
    print('Logged in as:', me)
    await r.close()
asyncio.run(test())
"
```

---

## Platform 2: Discord (~30 min)

### 1. Create a bot

- Go to https://discord.com/developers/applications
- **New Application** → name it `matchbot`
- Left menu: **Bot** → "Add Bot"
- Copy the **Token** → this is your `DISCORD_BOT_TOKEN`
- Enable these **Privileged Gateway Intents**:
  - Message Content Intent
  - Server Members Intent

### 2. Invite the bot to your server

- Left menu: **OAuth2 → URL Generator**
- Scopes: `bot`
- Bot Permissions: `Read Messages/View Channels`, `Send Messages`, `Read Message History`
- Open the generated URL and invite the bot to your server

### 3. Get the Guild ID and Channel IDs

- In Discord: **Settings → Advanced → enable Developer Mode**
- Right-click your server name → **Copy Server ID** → this is your `guild_id`
- Right-click each channel to monitor → **Copy Channel ID**

### 4. Update `sources.yaml`

```yaml
discord:
  guilds:
    - guild_id: "123456789012345678"
      name: "Rising Sparks"
      allowed_channel_ids:
        - "987654321098765432"   # #camp-finder
        - "111222333444555666"   # #seeking-camp
```

### 5. Fill in `.env`

```
DISCORD_ENABLED=true
DISCORD_BOT_TOKEN=MTExMjIy...
DISCORD_MODERATOR_CHANNEL_ID=987654321098765432
```

### 6. Test the connection

```bash
uv run python -c "
import asyncio, discord
async def test():
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)
    @client.event
    async def on_ready():
        print('Connected as', client.user)
        await client.close()
    await client.start('YOUR_TOKEN_HERE')
asyncio.run(test())
"
```

---

## Platform 3: Facebook (requires a public URL)

Facebook requires a publicly reachable HTTPS webhook. You need a tunnel for local dev.

### 1. Get a public URL

Use [ngrok](https://ngrok.com) or [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/):

```bash
ngrok http 8080
# → gives you something like https://abc123.ngrok.io
```

### 2. Create a Facebook App

- Go to https://developers.facebook.com/apps
- **Create App** → type: **Business**
- Add product: **Webhooks**
- Also add: **Groups API** (note: this requires App Review for production — see below)

### 3. Set up the Webhook

- Webhooks → New Subscription → **Groups**
- Callback URL: `https://abc123.ngrok.io/webhook/facebook`
- Verify Token: pick any random string (e.g. `burnerbot-secret-2025`) → this is your `FACEBOOK_VERIFY_TOKEN`
- Subscribe to fields: `feed`, `messages`

### 4. Get credentials

- App Settings → Basic → copy **App ID** and **App Secret**
- For Page Access Token: link a Facebook Page to your app, then Pages → Access Tokens → Generate

### 5. Fill in `.env`

```
FACEBOOK_ENABLED=true
FACEBOOK_APP_ID=123456789
FACEBOOK_APP_SECRET=abc...
FACEBOOK_PAGE_ACCESS_TOKEN=EAABsb...
FACEBOOK_VERIFY_TOKEN=burnerbot-secret-2025
```

### Note on Facebook Groups API permissions

Access to group posts requires the `groups_access_member_info` permission, which requires **Facebook App Review** for production use. For initial testing, add yourself as a test user in the app dashboard and use a group you administer.

### Historical Facebook group backfill

Historical group posts are handled separately from the webhook flow above. The repo includes a passive Chrome extension that captures Facebook's own GraphQL responses while you browse normally, plus a CLI importer that ingests the captured file.

This is the preferred approach because it does not synthesize scrolls or clicks. You browse the group yourself, the extension observes the network responses, and the Python script imports the results afterward.

#### Option A: bundled Chrome extension (recommended)

1. Load the unpacked extension:
   - Open Chrome or another Chromium browser
   - Go to `chrome://extensions`
   - Enable **Developer mode**
   - Click **Load unpacked**
   - Select `extensions/fb-group-collector/`

2. Start a capture session:
   - Open the target Facebook group in the same browser profile you normally use
   - Click the extension icon
   - Click **Start Capturing**
   - Scroll the group manually to load the posts you want

3. Download the capture:
   - Click **Download fb_posts.json**
   - The extension stops capture before starting the download so the file is less likely to miss the last buffered responses
   - Save the file somewhere local, for example `data/raw/facebook/fb_posts_2026-03-22.json`
   - Only click **Clear Storage** after the download succeeds

4. Import the capture:

```bash
uv run python scripts/backfill_facebook.py data/raw/facebook/fb_posts_2026-03-22.json \
  --group-name "Burning Man Theme Camps" \
  --group-id 1234567890 \
  --dry-run
```

If the dry run looks right, import for real:

```bash
uv run python scripts/backfill_facebook.py data/raw/facebook/fb_posts_2026-03-22.json \
  --group-name "Burning Man Theme Camps" \
  --group-id 1234567890 \
  --no-extract
```

Use `--no-extract` if you want to ingest the raw posts first and run extraction later. Omit it if you want the import to run LLM extraction during the backfill.

Useful options:

```bash
uv run python scripts/backfill_facebook.py data/raw/facebook/fb_posts_2026-03-22.json \
  --group-name "Burning Man Theme Camps" \
  --group-id 1234567890 \
  --since-date 2026-01-01 \
  --sleep-seconds 0.5
```

- `--since-date YYYY-MM-DD`: skip posts older than that UTC date
- `--dry-run`: parse and deduplicate only, with no DB writes
- `--no-extract`: save imported posts as `RAW` without calling the LLM extractor
- `--sleep-seconds`: pause between extraction calls when extraction is enabled

Operational notes:

- The extension is passive. It does not automate browsing.
- Captured data in extension storage is lost if the browser closes before you download it.
- `chrome.storage.session` has a 10 MB limit. If the popup warns that storage is nearly full, download and clear before continuing.
- Extension output contains Facebook post data and user identifiers. Treat it as sensitive local data.

#### Option B: HAR export fallback

If the extension stops working because Facebook changes its frontend behavior, you can fall back to a HAR export.

1. Open Chrome DevTools on the Facebook group page
2. Go to the **Network** tab
3. Enable **Preserve log**
4. Scroll the group manually
5. Export with **Save all as HAR with content**
6. Import the HAR with the same command:

```bash
uv run python scripts/backfill_facebook.py data/raw/facebook/session.har \
  --group-name "Burning Man Theme Camps" \
  --group-id 1234567890 \
  --dry-run
```

HAR files are higher risk than the extension output because they can contain cookies, auth headers, and unrelated browser traffic. Never commit them to git, and delete them when you are done.

#### Files involved

- `extensions/fb-group-collector/`: unpacked MV3 extension for passive capture
- `scripts/backfill_facebook.py`: CLI entry point
- `src/matchbot/importers/facebook_har.py`: HAR and extension JSON parser + ingestion logic

For design rationale and risk tradeoffs, see `docs/facebook-backfill-plan.md`.

---

## Moderator API credentials

The `/api/mod/` endpoints are protected by a password + HMAC-signed session cookie.

### Fill in `.env`

```
MOD_PASSWORD=choose-a-strong-password
MOD_SECRET_KEY=a-long-random-string-here
```

Generate a good secret key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Both values default to empty, which disables auth entirely (fine for local dev, **not for production**).

---

## Starting the full system

Once `.env` is filled in, enable the platforms you've configured (`REDDIT_ENABLED=true`, etc.):

```bash
uv run alembic upgrade head          # ensure DB schema is current
uv run python scripts/run_listeners.py
```

You should see log lines confirming each platform connected (or skipped):

```
INFO  matchbot.run — Database ready.
INFO  matchbot.run — Starting all listeners…
INFO  matchbot.run — Reddit disabled (REDDIT_ENABLED=false) — skipping Reddit listeners.
INFO  matchbot.run — Discord credentials not set — skipping Discord listener.
INFO  matchbot.listeners.discord_bot — Discord bot connected as matchbot#1234
```

Posts ingested from each platform will appear in `matchbot.db` with `status=RAW`, then progress through extraction and matching automatically.
