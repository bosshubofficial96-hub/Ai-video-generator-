# 🎬 BossHuBots AI Video Generator Bot v2

Full-featured AI video generation Telegram bot with its **own REST API server**, **web dashboard**, **own AI pipeline (text→image→video)**, **advanced inline control panels**, and **automatic retry/fallback** system.

## 🔥 What's New in v2

| Feature | v1 | v2 |
|---|---|---|
| AI models | 6 | 7 (+ Own Pipeline) |
| Own REST API | ❌ | ✅ Full CRUD API |
| Web Dashboard | ❌ | ✅ Live HTML dashboard |
| Own AI pipeline | ❌ | ✅ SD→SVD two-stage |
| Auto-retry | ❌ | ✅ 3 retries + fallback |
| Priority queue | ❌ | ✅ Premium users first |
| Generation cache | ❌ | ✅ 1-hour URL cache |
| Prompt enhancement | ❌ | ✅ Auto-enrichment |
| API tokens | ❌ | ✅ Full token management |
| Admin inline panel | Basic | Advanced multi-level |
| Settings panel | 6 options | 10 options incl. seed |

## 🚀 Quick Setup

```bash
# 1. Extract and enter directory
unzip BossHuBots-AI-VideoGen-Bot-v2.zip
cd BossHuBots-AI-VideoGen-Bot-v2

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
nano .env   # Fill in required values

# 4. Run
python bot.py
```

## ⚙️ Required .env Values

| Variable | Where to get |
|---|---|
| `API_ID` | https://my.telegram.org |
| `API_HASH` | https://my.telegram.org |
| `BOT_TOKEN` | @BotFather on Telegram |
| `DB_URL` | MongoDB Atlas: https://cloud.mongodb.com |
| `ADMIN` | Your Telegram numeric user ID |
| `REPLICATE_API_TOKEN` | https://replicate.com (free tier!) |

## 🌐 Own REST API

The bot starts its own HTTP server on `API_PORT` (default 8080).

**Auth:** All endpoints (except `/api/health`, `/api/models`, `/`) require a Bearer token.

Create a token via Telegram: `/create_api_token myapp admin`

### Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Web dashboard |
| GET | `/api/health` | Health check (no auth) |
| GET | `/api/stats` | Bot statistics |
| GET | `/api/users` | List recent users |
| GET | `/api/users/{id}` | User info |
| POST | `/api/users/{id}/premium` | Add premium `{days, plan}` |
| DELETE | `/api/users/{id}/premium` | Remove premium |
| POST | `/api/users/{id}/ban` | Ban user `{reason}` |
| DELETE | `/api/users/{id}/ban` | Unban user |
| GET | `/api/generations` | Recent generations |
| GET | `/api/models` | Available AI models |
| POST | `/api/broadcast` | Broadcast `{text}` |
| GET | `/api/fsub` | Force-sub channels |
| POST | `/api/fsub` | Add channel `{channel_id, invite_link, title}` |
| DELETE | `/api/fsub/{id}` | Remove channel |
| GET | `/api/maintenance` | Maintenance status |
| POST | `/api/maintenance` | Set maintenance `{enabled, message}` |
| GET | `/api/tokens` | List API tokens |
| POST | `/api/tokens` | Create token `{label, permissions}` |
| DELETE | `/api/tokens/{label}` | Revoke token |
| GET | `/api/queue` | Queue status |

### Example API Calls

```bash
# Health check
curl http://localhost:8080/api/health

# Stats (authenticated)
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8080/api/stats

# Add premium to a user (30 days)
curl -X POST -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"days":30,"plan":"Gold"}' \
  http://localhost:8080/api/users/123456789/premium

# Enable maintenance mode
curl -X POST -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled":true,"message":"🔧 Under maintenance!"}' \
  http://localhost:8080/api/maintenance
```

## 🤖 AI Models

| Model | Provider | Type | Free | Description |
|---|---|---|---|---|
| Zeroscope XL | Replicate | text→video | ✅ | Best free text-to-video |
| AnimateDiff | Replicate | text→video | ✅ | Smooth animations |
| Stable Video Diffusion | Replicate | image→video | ✅ | Animate any image |
| Hotshot XL | Replicate | text→GIF | ✅ | Animated GIFs |
| **BossHuBots Pipeline** | **Own** | **text→video** | **✅** | **Our own SD→SVD pipeline** |
| Luma Dream Machine | Luma API | text→video | 🔒 | Cinematic quality |
| Kling AI | Fal API | text→video | 🔒 | Ultra-realistic |

## 🔄 Own AI Pipeline (BossHuBots Pipeline)

Our two-stage pipeline runs entirely on Replicate:
1. **Stage 1:** Text → Image using SDXL (30 inference steps)
2. **Stage 2:** Image → Video using Stable Video Diffusion

This means you can get our "own" generation using only the Replicate free tier!

## 🔄 Auto-Retry & Fallback

The AI engine automatically:
1. Tries the selected model up to `MAX_RETRIES` (default 3) times
2. Waits `RETRY_DELAY_BASE * 2^retry` seconds between attempts
3. If all retries fail, tries the **next provider in the fallback chain**
4. Example chain: `zeroscope_xl → animatediff → own_pipeline`

## 📁 Project Structure

```
BossHuBots-AI-VideoGen-Bot-v2/
├── bot.py              # Entry point: bot + API server
├── api_server.py       # Own aiohttp REST API server
├── config.py           # All configuration
├── requirements.txt
├── .env.example
├── Procfile
├── helper/
│   ├── ai_engine.py    # Own AI engine: retry, fallback, cache, pipeline
│   ├── database.py     # MongoDB layer (users, gens, premium, tokens, queue)
│   └── utils.py        # Advanced keyboard builders (multi-level panels)
├── plugins/
│   ├── start.py        # /start, /help, /about, /stats, /plan, /history
│   ├── generate.py     # Generation engine integration + priority queue
│   ├── callbacks.py    # All 30+ inline button handlers
│   ├── admin.py        # Advanced admin panel + all admin commands
│   └── force_sub.py    # Dynamic force-subscribe
└── web/
    └── dashboard.html  # Live web admin dashboard (SPA)
```

## 🛠️ Admin Commands

```
/admin              — Open inline admin panel
/broadcast text     — Broadcast to all users
/ban uid reason     — Ban user
/unban uid          — Unban user
/add_premium uid days [plan]  — Add premium
/remove_premium uid — Remove premium
/add_fsub @channel  — Add force-sub channel
/remove_fsub @ch    — Remove force-sub channel
/list_fsub          — List force-sub channels
/maintenance_on [msg] — Enable maintenance
/maintenance_off    — Disable maintenance
/stats_full         — Full statistics + ping
/create_api_token label [perms]  — Create REST API token
/list_api_tokens    — List all tokens
/revoke_api_token label — Revoke a token
/logs               — Download bot log file
/restart            — Restart bot process
```

---
Made with ❤️ by @BossHuBots
