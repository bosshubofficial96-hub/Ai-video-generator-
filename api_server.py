"""
BossHuBots AI Video Generator — Own REST API Server
Runs alongside the bot on a configurable port.
Auth: Bearer token in Authorization header.

Endpoints:
  GET  /api/health
  GET  /api/stats
  GET  /api/users
  GET  /api/users/{id}
  POST /api/users/{id}/premium
  DELETE /api/users/{id}/premium
  POST /api/users/{id}/ban
  DELETE /api/users/{id}/ban
  GET  /api/generations
  GET  /api/models
  POST /api/broadcast
  GET  /api/fsub
  POST /api/fsub
  DELETE /api/fsub/{id}
  GET  /api/maintenance
  POST /api/maintenance
  GET  /api/tokens
  POST /api/tokens
  DELETE /api/tokens/{label}
  GET  /api/queue
  GET  /         → web dashboard
"""
import time, json, logging, asyncio
from aiohttp import web
from config import Config
from helper.database import db
from helper.utils import time_formatter

logger = logging.getLogger(__name__)

# ── Auth middleware ────────────────────────────────────────────

async def _auth(request: web.Request) -> dict | None:
    """Returns token doc or None if unauthorized."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        doc   = await db.validate_api_token(token)
        return doc
    # Also check ?api_key= query param
    api_key = request.rel_url.query.get("api_key", "")
    if api_key:
        return await db.validate_api_token(api_key)
    return None


def _require_perm(perm: str):
    """Decorator factory for permission checking."""
    def deco(fn):
        async def wrapper(request: web.Request):
            doc = await _auth(request)
            if not doc:
                raise web.HTTPUnauthorized(
                    text=json.dumps({"error": "Invalid or missing API token"}),
                    content_type="application/json"
                )
            perms = doc.get("permissions", [])
            if perm not in perms and "admin" not in perms:
                raise web.HTTPForbidden(
                    text=json.dumps({"error": f"Permission '{perm}' required"}),
                    content_type="application/json"
                )
            return await fn(request)
        wrapper.__name__ = fn.__name__
        return wrapper
    return deco


def json_resp(data: dict | list, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, default=str),
        content_type="application/json",
        status=status,
    )


# ── Route handlers ──────────────────────────────────────────────

async def health(request: web.Request) -> web.Response:
    return json_resp({
        "status": "ok",
        "version": Config.VERSION,
        "uptime": time_formatter(time.time() - Config.BOT_UPTIME),
        "timestamp": time.time(),
    })


@_require_perm("read")
async def stats(request: web.Request) -> web.Response:
    tu   = await db.total_users_count()
    tg   = await db.total_generations_count()
    tdg  = await db.today_generations_count()
    tfl  = await db.failed_generations_count()
    tp   = await db.total_premium_count()
    avg  = await db.avg_queue_wait()
    mnt, mmsg = await db.get_maintenance()
    sr   = round((tg - tfl) / tg * 100, 1) if tg else 0

    from plugins.generate import _gen_queue, _worker_running
    from helper.ai_engine import _url_cache

    return json_resp({
        "users":         {"total": tu, "premium": tp},
        "generations":   {"total": tg, "today": tdg, "failed": tfl, "success_rate": sr},
        "queue":         {"pending": _gen_queue.qsize(), "worker_running": _worker_running, "avg_wait_secs": avg},
        "cache":         {"entries": len(_url_cache)},
        "maintenance":   {"enabled": mnt, "message": mmsg},
        "uptime":        time_formatter(time.time() - Config.BOT_UPTIME),
    })


@_require_perm("read")
async def list_users(request: web.Request) -> web.Response:
    limit  = min(int(request.rel_url.query.get("limit", 50)), 200)
    recent = await db.get_recent_users(limit)
    out    = []
    for u in recent:
        is_prem = await db.has_premium_access(u.get("_id"))
        out.append({
            "id":         u.get("_id"),
            "join_date":  str(u.get("join_date","")),
            "total_gens": u.get("total_gens", 0),
            "daily_gens": u.get("daily_gens", 0),
            "is_premium": is_prem,
            "is_banned":  u.get("ban_status",{}).get("is_banned", False),
        })
    return json_resp(out)


@_require_perm("read")
async def get_user(request: web.Request) -> web.Response:
    uid = int(request.match_info["id"])
    u   = await db.get_user(uid)
    if not u:
        raise web.HTTPNotFound(text=json.dumps({"error": "User not found"}),
                                content_type="application/json")
    is_prem   = await db.has_premium_access(uid)
    remaining = await db.get_remaining_gens(uid)
    prem_info = await db.get_premium_info(uid) if is_prem else None
    return json_resp({
        "id":           uid,
        "join_date":    str(u.get("join_date","")),
        "total_gens":   u.get("total_gens", 0),
        "daily_gens":   u.get("daily_gens", 0),
        "remaining":    remaining,
        "is_premium":   is_prem,
        "premium_info": {
            "plan":   prem_info.get("plan") if prem_info else None,
            "expiry": str(prem_info.get("expiry","")) if prem_info else None,
        },
        "is_banned":    u.get("ban_status",{}).get("is_banned", False),
        "ban_reason":   u.get("ban_status",{}).get("reason",""),
        "settings":     u.get("settings", {}),
    })


@_require_perm("write")
async def add_user_premium(request: web.Request) -> web.Response:
    uid  = int(request.match_info["id"])
    body = await request.json()
    days = int(body.get("days", 30))
    plan = body.get("plan", "Premium")
    await db.add_premium(uid, days, plan)
    return json_resp({"ok": True, "message": f"Premium added: {days} days ({plan})"})


@_require_perm("write")
async def remove_user_premium(request: web.Request) -> web.Response:
    uid = int(request.match_info["id"])
    await db.remove_premium(uid)
    return json_resp({"ok": True})


@_require_perm("write")
async def ban_user(request: web.Request) -> web.Response:
    uid  = int(request.match_info["id"])
    body = await request.json()
    reason = body.get("reason", "API ban")
    await db.ban_user(uid, reason)
    return json_resp({"ok": True})


@_require_perm("write")
async def unban_user(request: web.Request) -> web.Response:
    uid = int(request.match_info["id"])
    await db.unban_user(uid)
    return json_resp({"ok": True})


@_require_perm("read")
async def list_generations(request: web.Request) -> web.Response:
    uid   = request.rel_url.query.get("user_id")
    limit = min(int(request.rel_url.query.get("limit", 20)), 100)
    if uid:
        hist = await db.get_user_history(int(uid), limit)
    else:
        cursor = db.gens.find({"status": "success"}).sort("created_at", -1).limit(limit)
        hist   = await cursor.to_list(length=limit)
    out = [{
        "id":         str(g.get("_id","")),
        "user_id":    g.get("user_id"),
        "prompt":     g.get("prompt",""),
        "model":      g.get("model",""),
        "provider":   g.get("provider",""),
        "status":     g.get("status",""),
        "resolution": g.get("resolution",""),
        "duration":   g.get("duration_secs",0),
        "retry_count":g.get("retry_count",0),
        "created_at": str(g.get("created_at","")),
    } for g in hist]
    return json_resp(out)


async def list_models(request: web.Request) -> web.Response:
    out = []
    for key, m in Config.MODELS.items():
        out.append({
            "key":         key,
            "name":        m["name"],
            "provider":    m["provider"],
            "type":        m["type"],
            "resolutions": m["resolutions"],
            "durations":   m["durations"],
            "free":        m["free"],
            "description": m["description"],
        })
    return json_resp(out)


@_require_perm("write")
async def broadcast_api(request: web.Request) -> web.Response:
    body = await request.json()
    text = body.get("text", "")
    if not text:
        raise web.HTTPBadRequest(text=json.dumps({"error": "text required"}),
                                  content_type="application/json")
    # Queue async broadcast — returns immediately
    asyncio.create_task(_do_broadcast(text))
    return json_resp({"ok": True, "message": "Broadcast queued"})


async def _do_broadcast(text: str):
    from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated
    async for u in await db.get_all_users():
        uid = u.get("_id")
        try:
            from bot import bot_instance
            await bot_instance.send_message(uid, text)
        except FloodWait as e: await asyncio.sleep(e.value)
        except (UserIsBlocked, InputUserDeactivated): await db.delete_user(uid)
        except Exception: pass


@_require_perm("read")
async def list_fsub(request: web.Request) -> web.Response:
    chs = await db.get_all_fsub_channels()
    return json_resp(chs)


@_require_perm("write")
async def add_fsub(request: web.Request) -> web.Response:
    body = await request.json()
    cid  = body.get("channel_id")
    link = body.get("invite_link","")
    title= body.get("title", str(cid))
    if not cid:
        raise web.HTTPBadRequest(text=json.dumps({"error": "channel_id required"}),
                                  content_type="application/json")
    is_new = await db.add_fsub_channel(int(cid), link, title)
    return json_resp({"ok": True, "added": is_new})


@_require_perm("write")
async def delete_fsub(request: web.Request) -> web.Response:
    cid = int(request.match_info["id"])
    ok  = await db.remove_fsub_channel(cid)
    return json_resp({"ok": ok})


@_require_perm("read")
async def get_maintenance(request: web.Request) -> web.Response:
    enabled, msg = await db.get_maintenance()
    return json_resp({"enabled": enabled, "message": msg})


@_require_perm("admin")
async def set_maintenance(request: web.Request) -> web.Response:
    body    = await request.json()
    enabled = bool(body.get("enabled", False))
    msg     = body.get("message", "")
    await db.set_maintenance(enabled, msg)
    return json_resp({"ok": True, "enabled": enabled})


@_require_perm("admin")
async def list_tokens(request: web.Request) -> web.Response:
    tokens = await db.list_api_tokens()
    return json_resp(tokens)


@_require_perm("admin")
async def create_token(request: web.Request) -> web.Response:
    body  = await request.json()
    label = body.get("label")
    perms = body.get("permissions", ["read"])
    if not label:
        raise web.HTTPBadRequest(text=json.dumps({"error": "label required"}),
                                  content_type="application/json")
    token = await db.create_api_token(label, 0, perms)
    return json_resp({"ok": True, "token": token, "label": label}, status=201)


@_require_perm("admin")
async def revoke_token(request: web.Request) -> web.Response:
    label = request.match_info["label"]
    ok    = await db.revoke_api_token(label)
    return json_resp({"ok": ok})


@_require_perm("read")
async def queue_status(request: web.Request) -> web.Response:
    try:
        from plugins.generate import _gen_queue, _worker_running
        qsize   = _gen_queue.qsize()
        running = _worker_running
    except Exception:
        qsize, running = 0, False
    avg = await db.avg_queue_wait()
    return json_resp({
        "pending":        qsize,
        "max_size":       Config.MAX_QUEUE_SIZE,
        "worker_running": running,
        "avg_wait_secs":  avg,
        "max_retries":    Config.MAX_RETRIES,
        "timeout_secs":   Config.GEN_TIMEOUT_SECS,
    })


# ── Web Dashboard ─────────────────────────────────────────────

async def dashboard(request: web.Request) -> web.Response:
    import os
    html_path = os.path.join(os.path.dirname(__file__), "web", "dashboard.html")
    try:
        with open(html_path, "r") as f:
            content = f.read()
        return web.Response(text=content, content_type="text/html")
    except FileNotFoundError:
        return web.Response(text="<h1>Dashboard not found</h1>", content_type="text/html")


# ── App builder ───────────────────────────────────────────────

def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get  ("/",                    dashboard)
    app.router.add_get  ("/api/health",          health)
    app.router.add_get  ("/api/stats",           stats)
    app.router.add_get  ("/api/users",           list_users)
    app.router.add_get  ("/api/users/{id}",      get_user)
    app.router.add_post ("/api/users/{id}/premium",   add_user_premium)
    app.router.add_delete("/api/users/{id}/premium",  remove_user_premium)
    app.router.add_post ("/api/users/{id}/ban",       ban_user)
    app.router.add_delete("/api/users/{id}/ban",      unban_user)
    app.router.add_get  ("/api/generations",     list_generations)
    app.router.add_get  ("/api/models",          list_models)
    app.router.add_post ("/api/broadcast",       broadcast_api)
    app.router.add_get  ("/api/fsub",            list_fsub)
    app.router.add_post ("/api/fsub",            add_fsub)
    app.router.add_delete("/api/fsub/{id}",      delete_fsub)
    app.router.add_get  ("/api/maintenance",     get_maintenance)
    app.router.add_post ("/api/maintenance",     set_maintenance)
    app.router.add_get  ("/api/tokens",          list_tokens)
    app.router.add_post ("/api/tokens",          create_token)
    app.router.add_delete("/api/tokens/{label}", revoke_token)
    app.router.add_get  ("/api/queue",           queue_status)
    return app


async def start_api_server():
    if not Config.API_ENABLED:
        logger.info("API server disabled (API_ENABLED=false)")
        return None
    app    = build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site   = web.TCPSite(runner, "0.0.0.0", Config.API_PORT)
    await site.start()
    logger.info(f"✅ API server started on port {Config.API_PORT}")
    return runner
