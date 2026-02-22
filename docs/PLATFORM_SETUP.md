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

`src/matchbot/config/sources.yaml` is already set with `BurningMan`, `BurnerCommunity`, and `thecampout`. Swap in a subreddit you control for initial testing.

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
