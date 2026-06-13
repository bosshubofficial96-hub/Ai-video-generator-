"""Advanced admin panel with inline controls and full management commands."""
import os, sys, time, asyncio, logging, datetime
from pyrogram import Client, filters
from pyrogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery)
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked
from config import Config
from helper.database import db
from helper.utils import admin_menu_keyboard, admin_users_keyboard, admin_engine_keyboard, time_formatter

logger = logging.getLogger(__name__)


@Client.on_message(filters.private & filters.command("admin") & filters.user(Config.ADMIN))
async def admin_cmd(client, message: Message):
    await _send_admin_panel(message.reply_text, client)


async def _send_admin_panel(reply_fn, client):
    tu  = await db.total_users_count()
    tg  = await db.total_generations_count()
    tdg = await db.today_generations_count()
    tp  = await db.total_premium_count()
    fsub= await db.get_all_fsub_channels()
    mnt, _ = await db.get_maintenance()
    upt = time_formatter(time.time() - Config.BOT_UPTIME)
    from helper.ai_engine import _url_cache
    cache_size = len(_url_cache)
    await reply_fn(
        f"<blockquote><b>🛠️ Admin Panel v{Config.VERSION}</b>\n\n"
        f"⏱ Uptime: <code>{upt}</code>\n"
        f"👥 Users: <code>{tu}</code>  💎 Premium: <code>{tp}</code>\n"
        f"🎬 Total: <code>{tg}</code>  📅 Today: <code>{tdg}</code>\n"
        f"📢 ForceSub: <code>{len(fsub)}</code>\n"
        f"♻️ Cache: <code>{cache_size}</code> entries\n"
        f"🔧 Maintenance: {'🔴 ON' if mnt else '🟢 OFF'}</blockquote>",
        reply_markup=admin_menu_keyboard()
    )


# ── Callback panel ─────────────────────────────────────────────

def _adm(cb):
    return cb.from_user.id in Config.ADMIN


@Client.on_callback_query(filters.regex("^adm_back$"))
async def adm_back_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    tu  = await db.total_users_count()
    tg  = await db.total_generations_count()
    tdg = await db.today_generations_count()
    tp  = await db.total_premium_count()
    fsub= await db.get_all_fsub_channels()
    mnt, _ = await db.get_maintenance()
    upt = time_formatter(time.time() - Config.BOT_UPTIME)
    from helper.ai_engine import _url_cache
    await cb.message.edit_text(
        f"<blockquote><b>🛠️ Admin Panel v{Config.VERSION}</b>\n\n"
        f"⏱ Uptime: <code>{upt}</code>\n"
        f"👥 Users: <code>{tu}</code>  💎 Premium: <code>{tp}</code>\n"
        f"🎬 Total: <code>{tg}</code>  📅 Today: <code>{tdg}</code>\n"
        f"📢 ForceSub: <code>{len(fsub)}</code>\n"
        f"♻️ Cache: <code>{len(_url_cache)}</code> entries\n"
        f"🔧 Maintenance: {'🔴 ON' if mnt else '🟢 OFF'}</blockquote>",
        reply_markup=admin_menu_keyboard()
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^adm_stats$"))
async def adm_stats_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    tu  = await db.total_users_count()
    tg  = await db.total_generations_count()
    tdg = await db.today_generations_count()
    tfl = await db.failed_generations_count()
    tp  = await db.total_premium_count()
    avg = await db.avg_queue_wait()
    upt = time_formatter(time.time() - Config.BOT_UPTIME)
    api_tokens = await db.list_api_tokens()
    success_rate = round((tg - tfl) / tg * 100, 1) if tg else 0
    await cb.message.edit_text(
        f"<blockquote>📊 <b>Full Statistics</b>\n\n"
        f"⏱ Uptime: <code>{upt}</code>\n\n"
        f"👥 Users: <code>{tu}</code>  💎 Premium: <code>{tp}</code>\n"
        f"🎬 Total videos: <code>{tg}</code>\n"
        f"📅 Today: <code>{tdg}</code>\n"
        f"❌ Failed: <code>{tfl}</code>  ✅ Rate: <code>{success_rate}%</code>\n"
        f"⏱ Avg wait: <code>{avg:.0f}s</code>\n"
        f"🔑 API Tokens: <code>{len(api_tokens)}</code></blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 Gen Stats",  callback_data="adm_gen_stats")],
            [InlineKeyboardButton("🔙 Admin Panel",callback_data="adm_back")],
        ])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^adm_gen_stats$"))
async def adm_gen_stats_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    await cb.answer("Fetching…")
    by_model = await db.get_generation_stats_by_model()
    by_day   = await db.get_generation_stats_by_day(7)
    text = "<blockquote>📈 <b>Generation Stats</b>\n\n<b>By Model:</b>\n"
    total = sum(x["count"] for x in by_model)
    for item in by_model[:8]:
        m     = Config.MODELS.get(item["_id"],{}).get("name", item["_id"])
        count = item["count"]
        pct   = int(count/total*100) if total else 0
        bar   = "█" * (pct//5) + "░" * (20 - pct//5)
        text += f"  {m[:18]}: {count} ({pct}%)\n"
    text += "\n<b>Last 7 Days:</b>\n"
    for d in by_day:
        text += f"  {d['_id']}: {d['count']} videos\n"
    text += "</blockquote>"
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back", callback_data="adm_back")
    ]]))


@Client.on_callback_query(filters.regex("^adm_users_menu$"))
async def adm_users_menu_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    tu = await db.total_users_count()
    await cb.message.edit_text(
        f"<blockquote>👥 <b>User Management</b>\n\nTotal: <code>{tu}</code></blockquote>",
        reply_markup=admin_users_keyboard()
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^adm_recent_users$"))
async def adm_recent_users_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    await cb.answer("Fetching…")
    users = await db.get_recent_users(10)
    text  = "<blockquote>👥 <b>Recent Users</b>\n\n"
    for u in users:
        uid = u.get("_id")
        jd  = u.get("join_date")
        jd_s = jd.strftime("%d/%m") if jd else "?"
        tg   = u.get("total_gens",0)
        prem = "💎" if await db.has_premium_access(uid) else ""
        text += f"{prem}<code>{uid}</code> — {jd_s} — 🎬{tg}\n"
    text += "</blockquote>"
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back", callback_data="adm_users_menu")
    ]]))


@Client.on_callback_query(filters.regex("^adm_premium_menu$"))
async def adm_premium_menu_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    tp = await db.total_premium_count()
    await cb.message.edit_text(
        f"<blockquote>💎 <b>Premium Management</b>\nActive: <code>{tp}</code>\n\n"
        f"/add_premium user_id days [plan]\n"
        f"/remove_premium user_id\n"
        f"/premium_list</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Premium List", callback_data="adm_prem_list")],
            [InlineKeyboardButton("🔙 Admin Panel",  callback_data="adm_back")],
        ])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^adm_prem_list$"))
async def adm_prem_list_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    await cb.answer("Fetching…")
    all_prem = await db.get_all_premium()
    count = 0
    text  = "<blockquote>💎 <b>Premium Users</b>\n\n"
    async for pu in all_prem:
        count += 1
        uid = pu.get("_id")
        exp = pu.get("expiry")
        td  = exp - datetime.datetime.utcnow() if exp else None
        left = f"{td.days}d" if td else "?"
        plan = pu.get("plan","Premium")
        text += f"{count}. <code>{uid}</code> — {plan} — {left}\n"
        if count >= 30: text += "…\n"; break
    text += f"\nTotal: {count}</blockquote>"
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back", callback_data="adm_premium_menu")
    ]]))


@Client.on_callback_query(filters.regex("^adm_ban_menu$"))
async def adm_ban_menu_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    await cb.message.edit_text(
        "<blockquote>🚫 <b>Ban Management</b>\n\n"
        "/ban user_id reason\n"
        "/unban user_id\n"
        "/banned_users</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Banned List", callback_data="adm_ban_list")],
            [InlineKeyboardButton("🔙 Admin Panel", callback_data="adm_back")],
        ])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^adm_ban_list$"))
async def adm_ban_list_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    await cb.answer("Fetching…")
    all_b  = await db.get_all_banned()
    count  = 0
    text   = "<blockquote>🚫 <b>Banned Users</b>\n\n"
    async for u in all_b:
        count += 1
        uid    = u.get("_id")
        reason = u.get("ban_status",{}).get("reason","?")[:30]
        text  += f"{count}. <code>{uid}</code> — {reason}\n"
        if count >= 30: text += "…\n"; break
    text += f"\nTotal: {count}</blockquote>" if count else "None.</blockquote>"
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back", callback_data="adm_ban_menu")
    ]]))


@Client.on_callback_query(filters.regex("^adm_fsub_menu$"))
async def adm_fsub_menu_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    channels = await db.get_all_fsub_channels()
    ch_text  = ""
    for i, ch in enumerate(channels, 1):
        ch_text += f"\n{i}. <b>{ch['title']}</b> (<code>{ch['channel_id']}</code>)"
    await cb.message.edit_text(
        f"<blockquote>📢 <b>Force Subscribe ({len(channels)} channels)</b>{ch_text}\n\n"
        f"/add_fsub @channel\n/remove_fsub @channel\n/list_fsub</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 Clear All",    callback_data="adm_fsub_clear_confirm")],
            [InlineKeyboardButton("🔙 Admin Panel",  callback_data="adm_back")],
        ])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^adm_fsub_clear_confirm$"))
async def adm_fsub_clear_confirm_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    await cb.message.edit_text(
        "<blockquote>⚠️ Clear ALL force-sub channels?</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes", callback_data="adm_fsub_clear_yes"),
             InlineKeyboardButton("❌ No",  callback_data="adm_fsub_menu")],
        ])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^adm_fsub_clear_yes$"))
async def adm_fsub_clear_yes_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    await db.clear_fsub_channels()
    await cb.message.edit_text(
        "<blockquote>✅ All force-sub channels cleared!</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Admin Panel", callback_data="adm_back")
        ]])
    )
    await cb.answer("Cleared!")


@Client.on_callback_query(filters.regex("^adm_maint_menu$"))
async def adm_maint_menu_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    maint, msg = await db.get_maintenance()
    await cb.message.edit_text(
        f"<blockquote>🔧 <b>Maintenance</b>\nStatus: {'🔴 ON' if maint else '🟢 OFF'}\n"
        f"{'Msg: ' + msg[:60] if msg else ''}</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴 Turn ON",  callback_data="adm_maint_on"),
             InlineKeyboardButton("🟢 Turn OFF", callback_data="adm_maint_off")],
            [InlineKeyboardButton("🔙 Admin Panel", callback_data="adm_back")],
        ])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^adm_maint_on$"))
async def adm_maint_on_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    await db.set_maintenance(True, "🔧 Bot under maintenance. Please try again later!")
    await cb.answer("🔴 ON")
    await cb.message.edit_text(
        "<blockquote>🔴 Maintenance ON!</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 Turn OFF",   callback_data="adm_maint_off")],
            [InlineKeyboardButton("🔙 Admin Panel",callback_data="adm_back")],
        ])
    )


@Client.on_callback_query(filters.regex("^adm_maint_off$"))
async def adm_maint_off_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    await db.set_maintenance(False, "")
    await cb.answer("🟢 OFF")
    await cb.message.edit_text(
        "<blockquote>🟢 Maintenance OFF!</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴 Turn ON",    callback_data="adm_maint_on")],
            [InlineKeyboardButton("🔙 Admin Panel",callback_data="adm_back")],
        ])
    )


@Client.on_callback_query(filters.regex("^adm_broadcast_info$"))
async def adm_broadcast_info_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    await cb.message.edit_text(
        "<blockquote>📢 <b>Broadcast</b>\n\n"
        "Reply to any message with /broadcast\n"
        "Or: /broadcast text to send\n\n"
        "Supports: text, photo, video, document, sticker</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Admin Panel", callback_data="adm_back")
        ]])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^adm_engine_menu$"))
async def adm_engine_menu_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    from plugins.generate import _gen_queue
    from helper.ai_engine import _url_cache
    qsize = _gen_queue.qsize()
    cache = len(_url_cache)
    await cb.message.edit_text(
        f"<blockquote>🤖 <b>AI Engine</b>\n\n"
        f"📋 Queue: <code>{qsize}</code> jobs pending\n"
        f"♻️ Cache: <code>{cache}</code> entries\n\n"
        f"Keys loaded:\n"
        f"  Replicate: {'✅' if Config.REPLICATE_API_TOKEN else '❌'}\n"
        f"  Luma AI:   {'✅' if Config.LUMA_API_KEY else '❌'}\n"
        f"  Fal/Kling: {'✅' if Config.FAL_API_KEY else '❌'}</blockquote>",
        reply_markup=admin_engine_keyboard()
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^adm_clear_cache$"))
async def adm_clear_cache_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    from helper.ai_engine import _url_cache
    count = len(_url_cache)
    _url_cache.clear()
    await cb.answer(f"✅ Cleared {count} cache entries")
    await cb.message.edit_text(
        f"<blockquote>✅ Cache cleared ({count} entries removed)</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Engine Menu", callback_data="adm_engine_menu")
        ]])
    )


@Client.on_callback_query(filters.regex("^adm_test_keys$"))
async def adm_test_keys_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    await cb.answer("Testing…")
    results = []
    if Config.REPLICATE_API_TOKEN:
        try:
            import replicate
            import os as _os
            _os.environ["REPLICATE_API_TOKEN"] = Config.REPLICATE_API_TOKEN
            list(replicate.models.list())
            results.append("Replicate ✅")
        except Exception as e:
            results.append(f"Replicate ❌ ({str(e)[:30]})")
    else:
        results.append("Replicate ❌ (not set)")
    results.append(f"Luma AI {'✅ (set)' if Config.LUMA_API_KEY else '❌ (not set)'}")
    results.append(f"Fal/Kling {'✅ (set)' if Config.FAL_API_KEY else '❌ (not set)'}")
    await cb.message.edit_text(
        "<blockquote>⚡ <b>API Key Test</b>\n\n" + "\n".join(results) + "</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Engine Menu", callback_data="adm_engine_menu")
        ]])
    )


@Client.on_callback_query(filters.regex("^adm_api_tokens$"))
async def adm_api_tokens_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    tokens = await db.list_api_tokens()
    text = "<blockquote>🔑 <b>API Tokens</b>\n\n"
    for t in tokens[:10]:
        rc   = t.get("request_count",0)
        perm = ", ".join(t.get("permissions",[]))
        lu   = t.get("last_used")
        lu_s = lu.strftime("%d/%m") if lu else "never"
        text += f"• <b>{t.get('label','?')}</b>  [{perm}]\n  Requests: {rc}  Last: {lu_s}\n\n"
    if not tokens:
        text += "No tokens yet.\n\n"
    text += (
        "Commands:\n"
        "/create_api_token label [read|write|admin]\n"
        "/list_api_tokens\n"
        "/revoke_api_token label</blockquote>"
    )
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Admin Panel", callback_data="adm_back")
    ]]))
    await cb.answer()


@Client.on_callback_query(filters.regex("^adm_logs$"))
async def adm_logs_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    await cb.answer("Sending log…")
    try:
        await client.send_document(cb.from_user.id, "BotLog.txt", caption="📥 Bot Log")
    except Exception as e:
        await cb.message.reply_text(f"<blockquote>❌ {e}</blockquote>")


@Client.on_callback_query(filters.regex("^adm_queue_status$"))
async def adm_queue_status_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    from plugins.generate import _gen_queue, _worker_running
    qsize = _gen_queue.qsize()
    avg   = await db.avg_queue_wait()
    await cb.message.edit_text(
        f"<blockquote>📋 <b>Queue Status</b>\n\n"
        f"Jobs pending: <code>{qsize}</code>\n"
        f"Worker running: {'✅' if _worker_running else '❌'}\n"
        f"Avg wait: <code>{avg:.0f}s</code>\n"
        f"Max size: <code>{Config.MAX_QUEUE_SIZE}</code>\n"
        f"Max retries: <code>{Config.MAX_RETRIES}</code></blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Engine Menu", callback_data="adm_engine_menu")
        ]])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^adm_restart_confirm$"))
async def adm_restart_confirm_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    await cb.message.edit_text(
        "<blockquote>🔄 Restart the bot?</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Restart", callback_data="adm_restart_yes"),
             InlineKeyboardButton("❌ Cancel",  callback_data="adm_back")],
        ])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^adm_restart_yes$"))
async def adm_restart_yes_cb(client, cb: CallbackQuery):
    if not _adm(cb): return await cb.answer("Admins only!", show_alert=True)
    await cb.message.edit_text("<blockquote>🔄 Restarting…</blockquote>")
    await cb.answer()
    await asyncio.sleep(1)
    os.execl(sys.executable, sys.executable, *sys.argv)


# ══════════ TEXT COMMANDS ══════════════════════════════════════

@Client.on_message(filters.private & filters.command("broadcast") & filters.user(Config.ADMIN))
async def broadcast_cmd(client, message: Message):
    bc = message.reply_to_message or (message if len(message.command) > 1 else None)
    if not bc:
        return await message.reply_text("<blockquote>Reply to a message or: /broadcast text</blockquote>")
    total  = await db.total_users_count()
    status = await message.reply_text(f"<blockquote>📢 Broadcasting to {total} users…</blockquote>")
    ok = fl = dead = 0
    async for u in await db.get_all_users():
        uid = u.get("_id")
        try:
            await bc.copy(chat_id=uid)
            ok += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try: await bc.copy(chat_id=uid); ok += 1
            except Exception: fl += 1
        except (InputUserDeactivated, UserIsBlocked):
            dead += 1
            await db.delete_user(uid)
        except Exception: fl += 1
        if (ok+fl+dead) % 100 == 0:
            try: await status.edit_text(f"<blockquote>📢 {ok} ✅  {fl} ❌  {dead} 👻</blockquote>")
            except Exception: pass
    await status.edit_text(
        f"<blockquote>✅ Broadcast done!\n✅ {ok}  ❌ {fl}  👻 {dead}</blockquote>"
    )


@Client.on_message(filters.private & filters.command("ban") & filters.user(Config.ADMIN))
async def ban_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("<blockquote>/ban user_id reason</blockquote>")
    try:
        uid    = int(message.command[1])
        reason = " ".join(message.command[2:]) or "Policy violation"
        await db.ban_user(uid, reason)
        try: await client.send_message(uid, f"<blockquote>🚫 Banned: {reason}</blockquote>")
        except Exception: pass
        await message.reply_text(f"<blockquote>✅ Banned <code>{uid}</code>\n{reason}</blockquote>")
    except Exception as e:
        await message.reply_text(f"<blockquote>❌ {e}</blockquote>")


@Client.on_message(filters.private & filters.command("unban") & filters.user(Config.ADMIN))
async def unban_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("<blockquote>/unban user_id</blockquote>")
    try:
        uid = int(message.command[1])
        await db.unban_user(uid)
        try: await client.send_message(uid, "<blockquote>✅ Your ban has been lifted!</blockquote>")
        except Exception: pass
        await message.reply_text(f"<blockquote>✅ Unbanned <code>{uid}</code></blockquote>")
    except Exception as e:
        await message.reply_text(f"<blockquote>❌ {e}</blockquote>")


@Client.on_message(filters.private & filters.command("add_premium") & filters.user(Config.ADMIN))
async def add_premium_cmd(client, message: Message):
    if len(message.command) < 3:
        return await message.reply_text("<blockquote>/add_premium user_id days [plan]</blockquote>")
    try:
        uid  = int(message.command[1])
        days = int(message.command[2])
        plan = message.command[3] if len(message.command) > 3 else "Premium"
        await db.add_premium(uid, days, plan)
        exp = (datetime.datetime.utcnow() + datetime.timedelta(days=days)).strftime("%d %b %Y")
        try: await client.send_message(uid,
            f"<blockquote>🎉 Premium activated!\nPlan: {plan}\nDays: {days}\nExpires: {exp}</blockquote>")
        except Exception: pass
        await message.reply_text(
            f"<blockquote>✅ Premium added!\nUser: <code>{uid}</code>\n{plan} · {days}d · {exp}</blockquote>"
        )
    except Exception as e:
        await message.reply_text(f"<blockquote>❌ {e}</blockquote>")


@Client.on_message(filters.private & filters.command("remove_premium") & filters.user(Config.ADMIN))
async def remove_premium_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("<blockquote>/remove_premium user_id</blockquote>")
    try:
        uid = int(message.command[1])
        await db.remove_premium(uid)
        await message.reply_text(f"<blockquote>✅ Premium removed for <code>{uid}</code></blockquote>")
    except Exception as e:
        await message.reply_text(f"<blockquote>❌ {e}</blockquote>")


@Client.on_message(filters.private & filters.command("add_fsub") & filters.user(Config.ADMIN))
async def add_fsub_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("<blockquote>/add_fsub @channel_or_id</blockquote>")
    raw = message.command[1]
    try: ref = int(raw)
    except ValueError: ref = raw
    proc = await message.reply_text("<blockquote>⏳ Validating…</blockquote>")
    try:
        chat = await client.get_chat(ref)
        try: link = chat.invite_link or await client.export_chat_invite_link(chat.id)
        except Exception: link = f"https://t.me/{chat.username}" if chat.username else ""
        is_new = await db.add_fsub_channel(chat.id, link, chat.title or str(chat.id))
        await proc.edit_text(
            f"<blockquote>✅ ForceSub {'Added' if is_new else 'Updated'}!\n"
            f"{chat.title} (<code>{chat.id}</code>)</blockquote>"
        )
    except Exception as e:
        await proc.edit_text(f"<blockquote>❌ {e}</blockquote>")


@Client.on_message(filters.private & filters.command("remove_fsub") & filters.user(Config.ADMIN))
async def remove_fsub_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("<blockquote>/remove_fsub @channel_or_id</blockquote>")
    raw = message.command[1]
    try: ref = int(raw)
    except ValueError: ref = raw
    cid = ref
    try: chat = await client.get_chat(ref); cid = chat.id
    except Exception: pass
    ok = await db.remove_fsub_channel(cid)
    await message.reply_text(f"<blockquote>{'✅ Removed' if ok else '❌ Not found'}: <code>{cid}</code></blockquote>")


@Client.on_message(filters.private & filters.command("list_fsub") & filters.user(Config.ADMIN))
async def list_fsub_cmd(client, message: Message):
    chs = await db.get_all_fsub_channels()
    if not chs:
        return await message.reply_text("<blockquote>📢 No force-sub channels.</blockquote>")
    text = "<blockquote>📢 <b>Force-Sub Channels</b>\n\n"
    for i, ch in enumerate(chs, 1):
        text += f"{i}. {ch['title']} (<code>{ch['channel_id']}</code>)\n"
    await message.reply_text(text + "</blockquote>")


@Client.on_message(filters.private & filters.command("maintenance_on") & filters.user(Config.ADMIN))
async def maint_on_cmd(client, message: Message):
    msg = " ".join(message.command[1:]) if len(message.command) > 1 else "🔧 Maintenance mode. Try later!"
    await db.set_maintenance(True, msg)
    await message.reply_text("<blockquote>🔴 Maintenance ON!</blockquote>")


@Client.on_message(filters.private & filters.command("maintenance_off") & filters.user(Config.ADMIN))
async def maint_off_cmd(client, message: Message):
    await db.set_maintenance(False, "")
    await message.reply_text("<blockquote>🟢 Maintenance OFF!</blockquote>")


@Client.on_message(filters.private & filters.command("stats_full") & filters.user(Config.ADMIN))
async def stats_full_cmd(client, message: Message):
    t0   = time.time()
    ping = await message.reply_text("⏱")
    ms   = (time.time() - t0) * 1000
    tu   = await db.total_users_count()
    tg   = await db.total_generations_count()
    tdg  = await db.today_generations_count()
    tfl  = await db.failed_generations_count()
    tp   = await db.total_premium_count()
    upt  = time_formatter(time.time() - Config.BOT_UPTIME)
    avg  = await db.avg_queue_wait()
    sr   = round((tg-tfl)/tg*100,1) if tg else 0
    await ping.edit_text(
        f"<blockquote>📊 <b>Full Stats</b>\n\n"
        f"⏱ Uptime: {upt}  🏓 {ms:.0f}ms\n"
        f"👥 Users: {tu}  💎 Premium: {tp}\n"
        f"🎬 Total: {tg}  📅 Today: {tdg}\n"
        f"❌ Failed: {tfl}  ✅ Rate: {sr}%\n"
        f"⏱ Avg wait: {avg:.0f}s</blockquote>"
    )


@Client.on_message(filters.private & filters.command("create_api_token") & filters.user(Config.ADMIN))
async def create_api_token_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("<blockquote>/create_api_token label [read|write|admin]</blockquote>")
    label = message.command[1]
    perms = message.command[2:] if len(message.command) > 2 else ["read"]
    token = await db.create_api_token(label, message.from_user.id, perms)
    await message.reply_text(
        f"<blockquote>🔑 <b>API Token Created!</b>\n\n"
        f"Label: {label}\nPerms: {', '.join(perms)}\n\n"
        f"Token:\n<code>{token}</code>\n\n"
        f"⚠️ Save this — it won't be shown again!</blockquote>"
    )


@Client.on_message(filters.private & filters.command("list_api_tokens") & filters.user(Config.ADMIN))
async def list_api_tokens_cmd(client, message: Message):
    tokens = await db.list_api_tokens()
    if not tokens:
        return await message.reply_text("<blockquote>🔑 No active API tokens.</blockquote>")
    text = "<blockquote>🔑 <b>API Tokens</b>\n\n"
    for t in tokens:
        rc   = t.get("request_count",0)
        perm = ", ".join(t.get("permissions",[]))
        text += f"• <b>{t['label']}</b>  [{perm}]  Requests: {rc}\n"
    await message.reply_text(text + "</blockquote>")


@Client.on_message(filters.private & filters.command("revoke_api_token") & filters.user(Config.ADMIN))
async def revoke_api_token_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("<blockquote>/revoke_api_token label</blockquote>")
    label = message.command[1]
    ok    = await db.revoke_api_token(label)
    await message.reply_text(
        f"<blockquote>{'✅ Revoked' if ok else '❌ Not found'}: {label}</blockquote>"
    )


@Client.on_message(filters.private & filters.command("restart") & filters.user(Config.ADMIN))
async def restart_cmd(client, message: Message):
    await message.reply_text("<blockquote>🔄 Restarting…</blockquote>")
    await asyncio.sleep(1)
    os.execl(sys.executable, sys.executable, *sys.argv)


@Client.on_message(filters.private & filters.command("logs") & filters.user(Config.ADMIN))
async def logs_cmd(client, message: Message):
    try: await message.reply_document("BotLog.txt")
    except Exception as e: await message.reply_text(f"<blockquote>❌ {e}</blockquote>")
