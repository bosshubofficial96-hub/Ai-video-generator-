"""All inline keyboard callbacks: menu nav, settings pickers, model/style/res/dur."""
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from helper.database import db
from helper.utils import (main_menu_keyboard, generate_panel, settings_panel,
                           model_keyboard, style_keyboard, resolution_keyboard,
                           duration_keyboard, quality_keyboard)


# ── Menu navigation ────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^menu_main$"))
async def menu_main_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    await db.add_user(uid)
    is_prem   = await db.has_premium_access(uid)
    remaining = await db.get_remaining_gens(uid)
    text = ("<blockquote><b>🎬 BossHuBots AI Video Generator v2</b>\n\n"
            "Own AI pipeline · Auto-retry · Prompt enhancement\n\n"
            "Choose an option 👇</blockquote>")
    try:
        await cb.message.edit_text(text, reply_markup=main_menu_keyboard(is_prem, remaining))
    except Exception:
        await cb.message.reply_text(text, reply_markup=main_menu_keyboard(is_prem, remaining))
    await cb.answer()


@Client.on_callback_query(filters.regex("^menu_generate$"))
async def menu_generate_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    await db.add_user(uid)
    maint, mmsg = await db.get_maintenance()
    if maint and uid not in Config.ADMIN:
        return await cb.answer(f"🔧 Maintenance: {mmsg[:80]}", show_alert=True)
    u = await db.get_user(uid) or {}
    s = u.get("settings", {})
    remaining = await db.get_remaining_gens(uid)
    from plugins.generate import _user_state
    _user_state[uid] = {"state": "awaiting_prompt", "settings": s}
    await cb.message.edit_text(
        "<blockquote>✏️ <b>Send Your Prompt</b>\n\n"
        "Type your video description, then adjust settings below.\n\n"
        "💡 Example:\n"
        "<i>A golden dragon flying over mountains at sunset, cinematic, 8K</i></blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings"),
             InlineKeyboardButton("❌ Cancel",   callback_data="cancel_gen")],
            [InlineKeyboardButton("🔙 Main Menu",callback_data="menu_main")],
        ])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^menu_img2vid$"))
async def menu_img2vid_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    u   = await db.get_user(uid) or {}
    s   = dict(u.get("settings", {}))
    s["model"] = "stable_video"
    from plugins.generate import _user_state
    _user_state[uid] = {"state": "awaiting_image", "settings": s}
    await cb.message.edit_text(
        "<blockquote>🖼️ <b>Image → Video</b>\n\nSend a photo to animate it!</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel",   callback_data="cancel_gen")],
            [InlineKeyboardButton("🔙 Main Menu",callback_data="menu_main")],
        ])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^menu_settings$"))
async def menu_settings_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    await db.add_user(uid)
    u = await db.get_user(uid) or {}
    s = u.get("settings", {})
    await cb.message.edit_text(
        "<blockquote>⚙️ <b>Settings</b>\n\nAll changes saved instantly.</blockquote>",
        reply_markup=settings_panel(s)
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^menu_history$"))
async def menu_history_cb(client, cb: CallbackQuery):
    uid  = cb.from_user.id
    hist = await db.get_user_history(uid, 8)
    if not hist:
        await cb.message.edit_text(
            "<blockquote>📜 No history yet!</blockquote>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎬 Generate Now", callback_data="menu_generate")],
                [InlineKeyboardButton("🔙 Back",         callback_data="menu_main")],
            ])
        )
        return await cb.answer()
    text = "<blockquote>📜 <b>Recent Generations</b>\n\n"
    for i, g in enumerate(hist, 1):
        p  = (g.get("prompt","?")[:35] + "…") if len(g.get("prompt","")) > 35 else g.get("prompt","?")
        m  = Config.MODELS.get(g.get("model",""),{}).get("name","?")
        ts = g.get("created_at")
        ts_s = ts.strftime("%d/%m %H:%M") if ts else "?"
        rc   = g.get("retry_count",0)
        text += f"{i}. <b>{p}</b>\n   🤖 {m} · {ts_s}{' 🔄' if rc else ''}\n\n"
    text += "</blockquote>"
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Generate Again", callback_data="menu_generate")],
        [InlineKeyboardButton("🔙 Back",           callback_data="menu_main")],
    ]))
    await cb.answer()


@Client.on_callback_query(filters.regex("^menu_stats$"))
async def menu_stats_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    u   = await db.get_user(uid) or {}
    s   = u.get("settings",{})
    is_prem   = await db.has_premium_access(uid)
    remaining = await db.get_remaining_gens(uid)
    lim = Config.PREMIUM_DAILY_GENS if is_prem else Config.FREE_DAILY_GENS
    model = Config.MODELS.get(s.get("model","zeroscope_xl"),{}).get("name","?")
    await cb.message.edit_text(
        f"<blockquote>📊 <b>Your Stats</b>\n\n"
        f"🎬 Total: <b>{u.get('total_gens',0)}</b>\n"
        f"📅 Today: <b>{u.get('daily_gens',0)}/{lim}</b>\n"
        f"⚡ Left: <b>{remaining}</b>\n"
        f"💎 Plan: {'Premium ✨' if is_prem else 'Free'}\n"
        f"🤖 Model: {model}</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 Upgrade" if not is_prem else "📜 History",
                                   callback_data="menu_plan" if not is_prem else "menu_history")],
            [InlineKeyboardButton("🔙 Back", callback_data="menu_main")],
        ])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^menu_plan$"))
async def menu_plan_cb(client, cb: CallbackQuery):
    uid     = cb.from_user.id
    is_prem = await db.has_premium_access(uid)
    if is_prem:
        pi = await db.get_premium_info(uid)
        import datetime
        exp  = pi["expiry"]
        td   = exp - datetime.datetime.utcnow()
        left = f"{td.days}d {td.seconds//3600}h"
        await cb.message.edit_text(
            f"<blockquote>💎 <b>{pi.get('plan','Premium')}</b>\n\n"
            f"⏳ {exp.strftime('%d %b %Y')} ({left} left)\n"
            f"🎬 {Config.PREMIUM_DAILY_GENS}/day  🤖 All models  ⚡ Priority</blockquote>",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="menu_main")
            ]])
        )
    else:
        rem = await db.get_remaining_gens(uid)
        await cb.message.edit_text(
            f"<blockquote>🆓 <b>Free Plan</b>  ⚡ {rem} left today\n\n"
            "💎 <b>Upgrade:</b>\n"
            "  🥉 7d — $5  |  🥈 30d — $15\n"
            "  🥇 90d — $35 |  💎 Lifetime — $99\n\n"
            "✅ Unlimited gens · All models · Priority queue\n"
            "Contact @BossHuBots to purchase.</blockquote>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Buy Premium", url=Config.SUPPORT_CHAT)],
                [InlineKeyboardButton("🔙 Back",        callback_data="menu_main")],
            ])
        )
    await cb.answer()


@Client.on_callback_query(filters.regex("^menu_models_info$"))
async def menu_models_info_cb(client, cb: CallbackQuery):
    text = "<blockquote>🤖 <b>Available AI Models</b>\n\n"
    for key, m in Config.MODELS.items():
        lock = "" if m["free"] else " 🔒 Premium"
        text += f"{m['icon']} <b>{m['name']}</b>{lock}\n  {m['description']}\n\n"
    text += "</blockquote>"
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Change Model", callback_data="pick_model")],
        [InlineKeyboardButton("🔙 Back",         callback_data="menu_main")],
    ]))
    await cb.answer()


@Client.on_callback_query(filters.regex("^menu_help$"))
async def menu_help_cb(client, cb: CallbackQuery):
    await cb.message.edit_text(
        "<blockquote>❓ <b>How to Use</b>\n\n"
        "1️⃣ Tap <b>🎬 Generate Video</b>\n"
        "2️⃣ Type your prompt\n"
        "3️⃣ Adjust model/style/resolution\n"
        "4️⃣ Tap <b>🚀 Generate Now</b>\n"
        "5️⃣ Get your video in 30–120s!\n\n"
        "🔄 <b>Auto-retry:</b> If one provider fails, we try the next automatically.\n"
        "🔥 <b>Own Pipeline:</b> Our SD→SVD two-stage pipeline.\n"
        "✨ <b>Enhance:</b> Auto-improves your prompt for better results.</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Generate Now", callback_data="menu_generate")],
            [InlineKeyboardButton("🔙 Back",         callback_data="menu_main")],
        ])
    )
    await cb.answer()


# ── Settings pickers ────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^pick_model$"))
async def pick_model_cb(client, cb: CallbackQuery):
    uid     = cb.from_user.id
    cur     = await db.get_user_setting(uid, "model", "zeroscope_xl")
    is_prem = await db.has_premium_access(uid)
    await cb.message.edit_text(
        "<blockquote>🤖 <b>Choose AI Model</b>\n🔒 = requires premium/API key</blockquote>",
        reply_markup=model_keyboard(cur, is_prem)
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^setmodel_(.+)$"))
async def setmodel_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    key = cb.data.split("_", 1)[1]
    m   = Config.MODELS.get(key)
    if not m: return await cb.answer("Unknown model!", show_alert=True)
    is_prem = await db.has_premium_access(uid)
    if not m.get("free") and not is_prem and uid not in Config.ADMIN:
        return await cb.answer(f"🔒 {m['name']} requires Premium!", show_alert=True)
    await db.update_user_setting(uid, "model",      key)
    await db.update_user_setting(uid, "resolution", m["resolutions"][0])
    await db.update_user_setting(uid, "duration",   m["durations"][0])
    await cb.answer(f"✅ Model: {m['name']}")
    u = await db.get_user(uid) or {}
    try:
        await cb.message.edit_text(
            f"<blockquote>✅ Model → <b>{m['name']}</b></blockquote>",
            reply_markup=settings_panel(u.get("settings",{}))
        )
    except Exception: pass


@Client.on_callback_query(filters.regex("^pick_style$"))
async def pick_style_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    cur = await db.get_user_setting(uid, "style", "realistic")
    await cb.message.edit_text(
        "<blockquote>🎨 <b>Choose Style Preset</b></blockquote>",
        reply_markup=style_keyboard(cur)
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^setstyle_(.+)$"))
async def setstyle_cb(client, cb: CallbackQuery):
    uid   = cb.from_user.id
    style = cb.data.split("_",1)[1]
    if style not in Config.STYLE_PRESETS:
        return await cb.answer("Unknown style!", show_alert=True)
    await db.update_user_setting(uid, "style", style)
    await cb.answer(f"✅ Style: {style.title()}")
    u = await db.get_user(uid) or {}
    try:
        await cb.message.edit_text(
            f"<blockquote>✅ Style → <b>{style.title()}</b></blockquote>",
            reply_markup=settings_panel(u.get("settings",{}))
        )
    except Exception: pass


@Client.on_callback_query(filters.regex("^pick_res$"))
async def pick_res_cb(client, cb: CallbackQuery):
    uid     = cb.from_user.id
    model   = await db.get_user_setting(uid, "model", "zeroscope_xl")
    current = await db.get_user_setting(uid, "resolution", "576x320")
    await cb.message.edit_text(
        "<blockquote>📐 <b>Choose Resolution</b></blockquote>",
        reply_markup=resolution_keyboard(model, current)
    )
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^setres_(\d+x\d+)$"))
async def setres_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    res = cb.data.split("_",1)[1]
    await db.update_user_setting(uid, "resolution", res)
    await cb.answer(f"✅ Resolution: {res}")
    u = await db.get_user(uid) or {}
    try:
        await cb.message.edit_text(
            f"<blockquote>✅ Resolution → <b>{res}</b></blockquote>",
            reply_markup=settings_panel(u.get("settings",{}))
        )
    except Exception: pass


@Client.on_callback_query(filters.regex("^pick_dur$"))
async def pick_dur_cb(client, cb: CallbackQuery):
    uid     = cb.from_user.id
    model   = await db.get_user_setting(uid, "model", "zeroscope_xl")
    current = await db.get_user_setting(uid, "duration", 3)
    await cb.message.edit_text(
        "<blockquote>⏱ <b>Choose Duration</b></blockquote>",
        reply_markup=duration_keyboard(model, current)
    )
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^setdur_(\d+)$"))
async def setdur_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    dur = int(cb.data.split("_",1)[1])
    await db.update_user_setting(uid, "duration", dur)
    await cb.answer(f"✅ Duration: {dur}s")
    u = await db.get_user(uid) or {}
    try:
        await cb.message.edit_text(
            f"<blockquote>✅ Duration → <b>{dur}s</b></blockquote>",
            reply_markup=settings_panel(u.get("settings",{}))
        )
    except Exception: pass


@Client.on_callback_query(filters.regex("^pick_quality$"))
async def pick_quality_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    cur = await db.get_user_setting(uid, "quality", "high")
    await cb.message.edit_text(
        "<blockquote>🔥 <b>Choose Quality</b></blockquote>",
        reply_markup=quality_keyboard(cur)
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^setquality_(.+)$"))
async def setquality_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    q   = cb.data.split("_",1)[1]
    await db.update_user_setting(uid, "quality", q)
    await cb.answer(f"✅ Quality: {q.title()}")
    u = await db.get_user(uid) or {}
    try:
        await cb.message.edit_text(
            f"<blockquote>✅ Quality → <b>{q.title()}</b></blockquote>",
            reply_markup=settings_panel(u.get("settings",{}))
        )
    except Exception: pass


@Client.on_callback_query(filters.regex("^toggle_enhance$"))
async def toggle_enhance_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    cur = await db.get_user_setting(uid, "enhance_prompt", True)
    await db.update_user_setting(uid, "enhance_prompt", not cur)
    await cb.answer(f"Prompt Enhance: {'ON' if not cur else 'OFF'}")
    u = await db.get_user(uid) or {}
    try:
        await cb.message.edit_reply_markup(settings_panel(u.get("settings",{})))
    except Exception: pass


@Client.on_callback_query(filters.regex("^toggle_notif$"))
async def toggle_notif_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    cur = await db.get_user_setting(uid, "notifications", True)
    await db.update_user_setting(uid, "notifications", not cur)
    await cb.answer(f"Notifications: {'ON' if not cur else 'OFF'}")
    u = await db.get_user(uid) or {}
    try:
        await cb.message.edit_reply_markup(settings_panel(u.get("settings",{})))
    except Exception: pass


@Client.on_callback_query(filters.regex("^set_negative$"))
async def set_negative_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    from plugins.generate import _user_state
    _user_state[uid] = {"state": "awaiting_negative"}
    cur = await db.get_user_setting(uid, "negative", Config.NEGATIVE_DEFAULT)
    await cb.message.edit_text(
        f"<blockquote>🚫 <b>Set Negative Prompt</b>\n\n"
        f"Current: <code>{cur[:100]}</code>\n\n"
        f"Type things you DON'T want in the video.</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data="menu_settings")
        ]])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^set_watermark$"))
async def set_watermark_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    from plugins.generate import _user_state
    _user_state[uid] = {"state": "awaiting_watermark"}
    await cb.message.edit_text(
        "<blockquote>🏷️ <b>Set Watermark</b>\n\nEnter watermark text (e.g. @MyChannel)</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 Clear",   callback_data="clear_watermark")],
            [InlineKeyboardButton("❌ Cancel",  callback_data="menu_settings")],
        ])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^clear_watermark$"))
async def clear_watermark_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    await db.update_user_setting(uid, "watermark", "")
    await cb.answer("✅ Watermark cleared")
    u = await db.get_user(uid) or {}
    await cb.message.edit_text(
        "<blockquote>✅ Watermark cleared.</blockquote>",
        reply_markup=settings_panel(u.get("settings",{}))
    )


@Client.on_callback_query(filters.regex("^set_seed$"))
async def set_seed_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    from plugins.generate import _user_state
    _user_state[uid] = {"state": "awaiting_seed"}
    cur = await db.get_user_setting(uid, "seed", -1)
    await cb.message.edit_text(
        f"<blockquote>🎲 <b>Set Seed</b>\n\nCurrent: <code>{cur}</code>\n\n"
        f"Enter a number for reproducible results, or -1 for random.</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Random (-1)", callback_data="set_seed_random")],
            [InlineKeyboardButton("❌ Cancel",      callback_data="menu_settings")],
        ])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^set_seed_random$"))
async def set_seed_random_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    await db.update_user_setting(uid, "seed", -1)
    await cb.answer("✅ Seed: Random")
    u = await db.get_user(uid) or {}
    await cb.message.edit_text(
        "<blockquote>✅ Seed → Random</blockquote>",
        reply_markup=settings_panel(u.get("settings",{}))
    )


@Client.on_callback_query(filters.regex("^reset_settings$"))
async def reset_settings_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    defaults = {
        "model": "zeroscope_xl", "style": "realistic",
        "resolution": "576x320", "duration": 3,
        "negative": Config.NEGATIVE_DEFAULT, "watermark": "",
        "enhance_prompt": True, "notifications": True,
        "quality": "high", "seed": -1,
    }
    await db.update_user(uid, {"settings": defaults})
    await cb.answer("✅ Settings reset to defaults")
    await cb.message.edit_text(
        "<blockquote>✅ Settings reset to defaults.</blockquote>",
        reply_markup=settings_panel(defaults)
    )


# ── ForceSub re-check ───────────────────────────────────────

@Client.on_callback_query(filters.regex("^fsub_check$"))
async def fsub_check_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    channels = await db.get_all_fsub_channels()
    if not channels:
        try: await cb.message.delete()
        except Exception: pass
        return await cb.answer("✅ No restrictions!", show_alert=True)
    from pyrogram import enums
    not_joined = []
    for ch in channels:
        try:
            member = await client.get_chat_member(ch["channel_id"], uid)
            if member.status not in [enums.ChatMemberStatus.MEMBER,
                                      enums.ChatMemberStatus.ADMINISTRATOR,
                                      enums.ChatMemberStatus.OWNER]:
                not_joined.append(ch.get("title","?"))
        except Exception:
            not_joined.append(ch.get("title","?"))
    if not_joined:
        await cb.answer(f"❌ Not joined: {', '.join(not_joined)}", show_alert=True)
    else:
        try: await cb.message.delete()
        except Exception: pass
        await cb.answer("✅ Verified! Enjoy the bot!", show_alert=True)
