import time
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from helper.database import db
from helper.utils import send_log, main_menu_keyboard, time_formatter

BANNER = "https://te.legra.ph/file/bosshubots-ai-video-gen.jpg"

@Client.on_message(filters.private & filters.command("start"))
async def start_cmd(client, message: Message):
    user = message.from_user
    await db.add_user(user.id)
    await send_log(client, user)
    if await db.is_banned(user.id):
        r = await db.get_ban_reason(user.id)
        return await message.reply_text(
            f"<blockquote>🚫 <b>You are banned!</b>\nReason: {r or 'Policy violation'}\n\nContact: @BossHuBots</blockquote>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Appeal",url=Config.SUPPORT_CHAT)]]))
    maint, mmsg = await db.get_maintenance()
    if maint and user.id not in Config.ADMIN:
        return await message.reply_text(f"<blockquote>🔧 <b>Under Maintenance</b>\n\n{mmsg}</blockquote>")
    is_prem   = await db.has_premium_access(user.id)
    remaining = await db.get_remaining_gens(user.id)
    text = (
        "<blockquote><b>🎬 BossHuBots AI Video Generator v2</b>\n\n"
        "Turn any <b>text prompt</b> into a stunning <b>AI-generated video</b>!\n\n"
        "🔥 <b>What's new in v2:</b>\n"
        "  • Own AI pipeline (text→image→video)\n"
        "  • Auto-retry with provider fallback\n"
        "  • Prompt enhancement engine\n"
        "  • REST API + Web dashboard\n"
        "  • Advanced inline control panels\n\n"
        "Pick an option below 👇</blockquote>"
    )
    try:
        await message.reply_photo(BANNER, caption=text, reply_markup=main_menu_keyboard(is_prem, remaining))
    except Exception:
        await message.reply_text(text, reply_markup=main_menu_keyboard(is_prem, remaining))

@Client.on_message(filters.private & filters.command("help"))
async def help_cmd(client, message: Message):
    await message.reply_text(
        "<blockquote><b>📖 Command Reference</b>\n\n"
        "<b>Generation:</b>\n"
        "  /generate [prompt] — Text to video\n"
        "  /img2vid           — Image to video\n\n"
        "<b>Settings:</b>\n"
        "  /settings — Full settings panel\n"
        "  /model    — Choose AI model\n"
        "  /style    — Choose style preset\n\n"
        "<b>Account:</b>\n"
        "  /stats   — Your usage stats\n"
        "  /history — Generation history\n"
        "  /plan    — Plan & limits\n\n"
        "<b>Admin only:</b>\n"
        "  /admin — Admin panel\n\n"
        "💡 Just send any text to start generating!</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Main Menu",callback_data="menu_main"),
             InlineKeyboardButton("💬 Support", url=Config.SUPPORT_CHAT)],
        ])
    )

@Client.on_message(filters.private & filters.command("about"))
async def about_cmd(client, message: Message):
    uptime     = time_formatter(time.time() - Config.BOT_UPTIME)
    tu = await db.total_users_count()
    tg = await db.total_generations_count()
    tp = await db.total_premium_count()
    await message.reply_text(
        f"<blockquote>🤖 <b>BossHuBots AI Video Generator</b>\n"
        f"Version: <code>{Config.VERSION}</code>\n\n"
        f"👥 Users: <code>{tu}</code>\n"
        f"🎬 Videos: <code>{tg}</code>\n"
        f"💎 Premium: <code>{tp}</code>\n"
        f"⏱ Uptime: {uptime}\n\n"
        f"Powered by Replicate · Luma AI · Kling AI · Own Pipeline\n"
        f"Support: @BossHuBots</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Main Menu",callback_data="menu_main"),
            InlineKeyboardButton("💬 Support",  url=Config.SUPPORT_CHAT),
        ]])
    )

@Client.on_message(filters.private & filters.command("stats"))
async def stats_cmd(client, message: Message):
    uid = message.from_user.id
    await db.add_user(uid)
    u   = await db.get_user(uid) or {}
    s   = u.get("settings", {})
    is_prem   = await db.has_premium_access(uid)
    remaining = await db.get_remaining_gens(uid)
    total_g   = u.get("total_gens", 0)
    daily_g   = u.get("daily_gens", 0)
    lim       = Config.PREMIUM_DAILY_GENS if is_prem else Config.FREE_DAILY_GENS
    model     = Config.MODELS.get(s.get("model","zeroscope_xl"),{}).get("name","?")
    await message.reply_text(
        f"<blockquote>📊 <b>Your Stats</b>\n\n"
        f"👤 {message.from_user.mention}\n"
        f"🆔 <code>{uid}</code>\n"
        f"💎 Plan: {'Premium ✨' if is_prem else 'Free'}\n\n"
        f"🎬 Total Generated: <b>{total_g}</b>\n"
        f"📅 Today: <b>{daily_g}/{lim}</b>\n"
        f"⚡ Remaining: <b>{remaining}</b>\n"
        f"🤖 Preferred Model: {model}</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Generate",  callback_data="menu_generate"),
             InlineKeyboardButton("💎 Upgrade",   callback_data="menu_plan")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="menu_main")],
        ])
    )

@Client.on_message(filters.private & filters.command("plan"))
async def plan_cmd(client, message: Message):
    uid = message.from_user.id
    is_prem = await db.has_premium_access(uid)
    if is_prem:
        pi = await db.get_premium_info(uid)
        import datetime
        exp    = pi["expiry"]
        td     = exp - datetime.datetime.utcnow()
        left   = f"{td.days}d {td.seconds//3600}h"
        plan   = pi.get("plan","Premium")
        await message.reply_text(
            f"<blockquote>💎 <b>Plan: {plan}</b>\n\n"
            f"⏳ Expires: {exp.strftime('%d %b %Y')} ({left} left)\n"
            f"🎬 Daily: {Config.PREMIUM_DAILY_GENS} videos\n"
            f"🤖 All models unlocked ✅\n"
            f"⚡ Priority queue ✅\n"
            f"🔄 Auto-retry ✅</blockquote>",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Main Menu", callback_data="menu_main")
            ]])
        )
    else:
        rem = await db.get_remaining_gens(uid)
        await message.reply_text(
            f"<blockquote>🆓 <b>Free Plan</b>\n\n"
            f"🎬 Daily: {Config.FREE_DAILY_GENS} videos  ⚡ Left: {rem}\n\n"
            f"<b>💎 Upgrade to Premium:</b>\n"
            f"  🥉 7 days  — $5\n"
            f"  🥈 30 days — $15\n"
            f"  🥇 90 days — $35\n"
            f"  💎 Lifetime — $99\n\n"
            f"Perks: unlimited gens · all models · priority queue\n"
            f"Contact @BossHuBots to upgrade.</blockquote>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Buy Premium", url=Config.SUPPORT_CHAT)],
                [InlineKeyboardButton("🏠 Main Menu",   callback_data="menu_main")],
            ])
        )

@Client.on_message(filters.private & filters.command("history"))
async def history_cmd(client, message: Message):
    uid  = message.from_user.id
    hist = await db.get_user_history(uid, 10)
    if not hist:
        return await message.reply_text(
            "<blockquote>📜 No history yet. Generate your first video!</blockquote>",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎬 Generate Now", callback_data="menu_generate")
            ]])
        )
    text = "<blockquote>📜 <b>Your Recent Generations</b>\n\n"
    for i, g in enumerate(hist, 1):
        p = g.get("prompt","?")[:40] + ("…" if len(g.get("prompt",""))>40 else "")
        m = Config.MODELS.get(g.get("model",""),{}).get("name","?")
        ts = g.get("created_at")
        ts_s = ts.strftime("%d/%m %H:%M") if ts else "?"
        rc   = g.get("retry_count",0)
        retry_info = f" 🔄×{rc}" if rc else ""
        text += f"{i}. <b>{p}</b>\n   🤖 {m} · {ts_s}{retry_info}\n\n"
    text += "</blockquote>"
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Generate Again", callback_data="menu_generate")],
        [InlineKeyboardButton("🏠 Main Menu",      callback_data="menu_main")],
    ]))

@Client.on_message(filters.private & filters.command("settings"))
async def settings_cmd(client, message: Message):
    uid = message.from_user.id
    await db.add_user(uid)
    u = await db.get_user(uid) or {}
    s = u.get("settings", {})
    from helper.utils import settings_panel
    await message.reply_text(
        "<blockquote>⚙️ <b>Your Settings</b>\n\nAll changes saved immediately.</blockquote>",
        reply_markup=settings_panel(s)
    )
