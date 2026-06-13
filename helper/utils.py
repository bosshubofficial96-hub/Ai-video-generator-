import time, os, aiohttp, asyncio, logging
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import Config

logger = logging.getLogger(__name__)


def humanbytes(size):
    if not size: return "0 B"
    for u in ["B","KB","MB","GB"]:
        if size < 1024: return f"{size:.1f} {u}"
        size /= 1024
    return f"{size:.1f} TB"

def time_formatter(secs):
    secs = int(secs)
    d, secs = divmod(secs, 86400)
    h, secs = divmod(secs, 3600)
    m, s    = divmod(secs, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)

def progress_bar(pct, length=18):
    filled = int(pct / 100 * length)
    return "█" * filled + "░" * (length - filled)

def pct_label(pct):
    return f"{progress_bar(pct)} {pct}%"

async def send_log(bot, user):
    if not Config.LOG_CHANNEL: return
    try:
        await bot.send_message(
            Config.LOG_CHANNEL,
            f"**New User** 🆕\n👤 {user.mention}\n🆔 `{user.id}`\n@{user.username or 'no_user'}"
        )
    except Exception: pass

async def download_file(url, dest):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=180)) as r:
                if r.status == 200:
                    with open(dest, "wb") as f:
                        async for chunk in r.content.iter_chunked(65536):
                            f.write(chunk)
                    return True
        return False
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return False

async def remove_file(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p): os.remove(p)
        except Exception: pass


# ═══════════════════════════════════════════════════════════
#   KEYBOARD BUILDERS — multi-level advanced inline panels
# ═══════════════════════════════════════════════════════════

# ── Main Menu ─────────────────────────────────────────────────

def main_menu_keyboard(is_premium: bool, remaining: int) -> InlineKeyboardMarkup:
    plan = "💎 Premium" if is_premium else "🆓 Free"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Generate Video",    callback_data="menu_generate"),
         InlineKeyboardButton("🖼️ Image → Video",    callback_data="menu_img2vid")],
        [InlineKeyboardButton("⚙️ Settings",          callback_data="menu_settings"),
         InlineKeyboardButton("📜 History",           callback_data="menu_history")],
        [InlineKeyboardButton("📊 My Stats",          callback_data="menu_stats"),
         InlineKeyboardButton(f"{plan} ({remaining} left)", callback_data="menu_plan")],
        [InlineKeyboardButton("🤖 Models",            callback_data="menu_models_info"),
         InlineKeyboardButton("❓ Help",              callback_data="menu_help")],
        [InlineKeyboardButton("💬 Support",           url=Config.SUPPORT_CHAT)],
    ])


# ── Generate launch panel ─────────────────────────────────────

def generate_panel(s: dict, remaining: int) -> InlineKeyboardMarkup:
    m    = Config.MODELS.get(s.get("model","zeroscope_xl"), {})
    st   = s.get("style","realistic").title()
    res  = s.get("resolution","576x320")
    dur  = s.get("duration",3)
    enh  = "✅" if s.get("enhance_prompt", True) else "❌"
    qual = s.get("quality","high").title()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🤖  Model:  {m.get('icon','')} {m.get('name','?')}", callback_data="pick_model")],
        [InlineKeyboardButton(f"🎨 Style: {st}",    callback_data="pick_style"),
         InlineKeyboardButton(f"📐 Res: {res}",     callback_data="pick_res")],
        [InlineKeyboardButton(f"⏱ Dur: {dur}s",    callback_data="pick_dur"),
         InlineKeyboardButton(f"✨ Enhance: {enh}", callback_data="toggle_enhance")],
        [InlineKeyboardButton(f"🔥 Quality: {qual}", callback_data="pick_quality")],
        [InlineKeyboardButton(f"🚀  GENERATE  ({remaining} left)", callback_data="do_generate")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")],
    ])


# ── Settings panel ────────────────────────────────────────────

def settings_panel(s: dict) -> InlineKeyboardMarkup:
    m    = Config.MODELS.get(s.get("model","zeroscope_xl"), {})
    st   = s.get("style","realistic").title()
    res  = s.get("resolution","576x320")
    dur  = s.get("duration",3)
    enh  = "ON ✅" if s.get("enhance_prompt",True) else "OFF ❌"
    notif= "ON 🔔" if s.get("notifications",True)  else "OFF 🔕"
    neg  = "✅" if s.get("negative","") else "❌"
    wm   = "✅" if s.get("watermark","") else "❌"
    seed = s.get("seed",-1)
    seed_lbl = "Random" if seed == -1 else str(seed)
    qual = s.get("quality","high").title()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🤖 Model: {m.get('name','?')}", callback_data="pick_model")],
        [InlineKeyboardButton(f"🎨 Style: {st}",      callback_data="pick_style"),
         InlineKeyboardButton(f"📐 Res: {res}",       callback_data="pick_res")],
        [InlineKeyboardButton(f"⏱ Duration: {dur}s", callback_data="pick_dur"),
         InlineKeyboardButton(f"🔥 Quality: {qual}",  callback_data="pick_quality")],
        [InlineKeyboardButton(f"✨ Prompt Enhance: {enh}", callback_data="toggle_enhance")],
        [InlineKeyboardButton(f"🚫 Neg Prompt: {neg}",     callback_data="set_negative"),
         InlineKeyboardButton(f"🏷️ Watermark: {wm}",     callback_data="set_watermark")],
        [InlineKeyboardButton(f"🎲 Seed: {seed_lbl}",     callback_data="set_seed"),
         InlineKeyboardButton(f"🔔 Notifs: {notif}",     callback_data="toggle_notif")],
        [InlineKeyboardButton("🔄 Reset Defaults",         callback_data="reset_settings")],
        [InlineKeyboardButton("🔙 Main Menu",              callback_data="menu_main")],
    ])


# ── Model picker ──────────────────────────────────────────────

def model_keyboard(current: str, is_premium: bool) -> InlineKeyboardMarkup:
    rows = []
    for key, m in Config.MODELS.items():
        tick  = "✅ " if key == current else ""
        lock  = "" if (m["free"] or is_premium) else " 🔒"
        rows.append([InlineKeyboardButton(
            f"{tick}{m['icon']} {m['name']}{lock}  —  {m['description'][:28]}",
            callback_data=f"setmodel_{key}"
        )])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="menu_settings")])
    return InlineKeyboardMarkup(rows)


# ── Style picker ──────────────────────────────────────────────

_STYLE_ICONS = {"realistic":"📷","cinematic":"🎥","anime":"⛩️","cartoon":"🎨",
                "abstract":"🌀","dark":"🌑","nature":"🌿","scifi":"🚀"}

def style_keyboard(current: str) -> InlineKeyboardMarkup:
    rows, row = [], []
    for key in Config.STYLE_PRESETS:
        tick = "✅ " if key == current else ""
        row.append(InlineKeyboardButton(
            f"{tick}{_STYLE_ICONS.get(key,'✨')} {key.title()}",
            callback_data=f"setstyle_{key}"
        ))
        if len(row) == 2:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="menu_settings")])
    return InlineKeyboardMarkup(rows)


# ── Resolution picker ─────────────────────────────────────────

def resolution_keyboard(model_key: str, current: str) -> InlineKeyboardMarkup:
    resolutions = Config.MODELS.get(model_key, {}).get("resolutions", ["512x512"])
    rows = []
    for r in resolutions:
        w, h   = map(int, r.split("x"))
        aspect = f"{'16:9' if w>h else ('9:16' if h>w else '1:1')}"
        tick   = "✅ " if r == current else ""
        rows.append([InlineKeyboardButton(f"{tick}📐 {r}  ({aspect})", callback_data=f"setres_{r}")])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="menu_settings")])
    return InlineKeyboardMarkup(rows)


# ── Duration picker ───────────────────────────────────────────

def duration_keyboard(model_key: str, current: int) -> InlineKeyboardMarkup:
    durations = Config.MODELS.get(model_key, {}).get("durations", [3])
    row = []
    for d in durations:
        tick = "✅ " if d == current else ""
        row.append(InlineKeyboardButton(f"{tick}⏱ {d}s", callback_data=f"setdur_{d}"))
    rows = [row, [InlineKeyboardButton("🔙 Back", callback_data="menu_settings")]]
    return InlineKeyboardMarkup(rows)


# ── Quality picker ────────────────────────────────────────────

def quality_keyboard(current: str) -> InlineKeyboardMarkup:
    options = [
        ("low",    "⚡ Fast (Low)",    "Faster, less detail"),
        ("medium", "⚖️ Balanced",      "Speed vs quality balance"),
        ("high",   "🔥 High Quality",  "Best results, slower"),
    ]
    rows = []
    for key, label, desc in options:
        tick = "✅ " if key == current else ""
        rows.append([InlineKeyboardButton(f"{tick}{label}  —  {desc}", callback_data=f"setquality_{key}")])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="menu_settings")])
    return InlineKeyboardMarkup(rows)


# ── Admin main menu ───────────────────────────────────────────

def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Live Stats",       callback_data="adm_stats"),
         InlineKeyboardButton("👥 Users",            callback_data="adm_users_menu")],
        [InlineKeyboardButton("💎 Premium Mgmt",     callback_data="adm_premium_menu"),
         InlineKeyboardButton("🚫 Ban Mgmt",         callback_data="adm_ban_menu")],
        [InlineKeyboardButton("📢 ForceSub",         callback_data="adm_fsub_menu"),
         InlineKeyboardButton("🔧 Maintenance",      callback_data="adm_maint_menu")],
        [InlineKeyboardButton("📢 Broadcast",        callback_data="adm_broadcast_info"),
         InlineKeyboardButton("🤖 AI Engine",        callback_data="adm_engine_menu")],
        [InlineKeyboardButton("🔑 API Tokens",       callback_data="adm_api_tokens"),
         InlineKeyboardButton("📈 Generation Stats", callback_data="adm_gen_stats")],
        [InlineKeyboardButton("📥 Logs",             callback_data="adm_logs"),
         InlineKeyboardButton("🔄 Restart",          callback_data="adm_restart_confirm")],
    ])


# ── Admin: Users sub-menu ─────────────────────────────────────

def admin_users_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Recent Users",    callback_data="adm_recent_users"),
         InlineKeyboardButton("📊 User Stats",      callback_data="adm_user_stats")],
        [InlineKeyboardButton("🔍 Lookup User",     callback_data="adm_lookup_user")],
        [InlineKeyboardButton("🔙 Admin Panel",     callback_data="adm_back")],
    ])


# ── Admin: AI Engine sub-menu ─────────────────────────────────

def admin_engine_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Queue Status",    callback_data="adm_queue_status"),
         InlineKeyboardButton("🧹 Clear Cache",     callback_data="adm_clear_cache")],
        [InlineKeyboardButton("📋 Model Stats",     callback_data="adm_model_stats"),
         InlineKeyboardButton("⚡ Test API Keys",   callback_data="adm_test_keys")],
        [InlineKeyboardButton("🔙 Admin Panel",     callback_data="adm_back")],
    ])
