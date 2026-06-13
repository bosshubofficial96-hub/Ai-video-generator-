"""
Advanced generation plugin — uses own AI engine with retry/fallback,
priority queue, live progress updates, full state machine.
"""
import asyncio, os, time, logging, tempfile
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from helper.database import db
from helper.utils import generate_panel, download_file, remove_file, progress_bar, time_formatter
from helper.ai_engine import generate_video

logger = logging.getLogger(__name__)

_user_state: dict = {}
_gen_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
_worker_running = False


# ── Guards ─────────────────────────────────────────────────────

async def _can_generate(uid, reply_target) -> bool:
    if await db.is_banned(uid):
        r = await db.get_ban_reason(uid)
        await reply_target.reply_text(f"<blockquote>🚫 Banned: {r}\nContact @BossHuBots</blockquote>")
        return False
    maint, mmsg = await db.get_maintenance()
    if maint and uid not in Config.ADMIN:
        await reply_target.reply_text(f"<blockquote>🔧 Maintenance: {mmsg}</blockquote>")
        return False
    if await db.get_remaining_gens(uid) <= 0:
        is_prem = await db.has_premium_access(uid)
        lim = Config.PREMIUM_DAILY_GENS if is_prem else Config.FREE_DAILY_GENS
        await reply_target.reply_text(
            f"<blockquote>⚠️ <b>Daily limit reached!</b>\n{lim} videos/day used.\n"
            f"{'Try tomorrow.' if is_prem else 'Upgrade: /plan'}</blockquote>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Upgrade",   callback_data="menu_plan")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="menu_main")],
            ])
        )
        return False
    if _gen_queue.qsize() >= Config.MAX_QUEUE_SIZE:
        await reply_target.reply_text(
            f"<blockquote>⏳ Queue full ({Config.MAX_QUEUE_SIZE} slots). Try again shortly!</blockquote>"
        )
        return False
    return True


# ── Photo downloader (passed to ai_engine) ────────────────────

def _make_photo_dl(client):
    async def _dl(file_id) -> str:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            path = tmp.name
        result = await client.download_media(file_id, file_name=path)
        return result or path
    return _dl


# ── Entry commands ─────────────────────────────────────────────

@Client.on_message(filters.private & filters.command(["generate","gen","video","prompt"]))
async def generate_cmd(client, message: Message):
    uid = message.from_user.id
    await db.add_user(uid)
    if not await _can_generate(uid, message): return
    u  = await db.get_user(uid) or {}
    s  = u.get("settings", {})
    inline_prompt = " ".join(message.command[1:]).strip()
    remaining = await db.get_remaining_gens(uid)
    if inline_prompt:
        _user_state[uid] = {"state":"confirm","prompt":inline_prompt,"settings":s}
        return await _show_confirm(message, uid, inline_prompt, s, remaining)
    _user_state[uid] = {"state":"awaiting_prompt","settings":s}
    await message.reply_text(
        "<blockquote>✏️ <b>Send Your Video Prompt</b>\n\n"
        "Describe the video you want to create.\n\n"
        "💡 Examples:\n"
        "  • A wolf running through snow at night\n"
        "  • Neon-lit Tokyo streets, slow camera pan\n"
        "  • Astronaut dancing on moon, 8K quality</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Quick Settings", callback_data="menu_settings"),
             InlineKeyboardButton("❌ Cancel",          callback_data="cancel_gen")],
        ])
    )


@Client.on_message(filters.private & filters.command("img2vid"))
async def img2vid_cmd(client, message: Message):
    uid = message.from_user.id
    await db.add_user(uid)
    if not await _can_generate(uid, message): return
    u = await db.get_user(uid) or {}
    s = dict(u.get("settings", {}))
    s["model"] = "stable_video"
    if message.reply_to_message and message.reply_to_message.photo:
        _user_state[uid] = {
            "state":"has_image",
            "photo_file_id": message.reply_to_message.photo.file_id,
            "settings": s,
        }
        return await _img_ready_msg(message)
    _user_state[uid] = {"state":"awaiting_image","settings":s}
    await message.reply_text(
        "<blockquote>🖼️ <b>Image to Video</b>\n\nSend a photo to animate it!</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_gen")
        ]])
    )


async def _img_ready_msg(target):
    await target.reply_text(
        "<blockquote>✅ <b>Image ready!</b>\n\nGenerate with auto motion or add a prompt.</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ Auto Motion",   callback_data="do_img2vid_auto")],
            [InlineKeyboardButton("✏️ Add Prompt",   callback_data="img2vid_add_prompt")],
            [InlineKeyboardButton("❌ Cancel",        callback_data="cancel_gen")],
        ])
    )


# ── Incoming text / photo collection ─────────────────────────

@Client.on_message(filters.private & filters.photo)
async def photo_handler(client, message: Message):
    uid = message.from_user.id
    sd  = _user_state.get(uid, {})
    if sd.get("state") == "awaiting_image":
        sd["state"]          = "has_image"
        sd["photo_file_id"]  = message.photo.file_id
        _user_state[uid]     = sd
        return await _img_ready_msg(message)
    _user_state[uid] = {"state":"last_photo",
                         "photo_file_id": message.photo.file_id,
                         "settings": (await db.get_user(uid) or {}).get("settings",{})}
    await message.reply_text(
        "<blockquote>🖼️ Animate this image?</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🎬 Animate It!", callback_data="start_img2vid_last")
        ]])
    )


_IGNORE_CMDS = {"start","help","about","stats","plan","history","generate","gen","video",
                "img2vid","settings","model","style","negative","admin","broadcast","ban",
                "unban","add_premium","remove_premium","premium_list","add_fsub","remove_fsub",
                "list_fsub","maintenance_on","maintenance_off","logs","restart","stats_full",
                "prompt","support","create_api_token","list_api_tokens","revoke_api_token"}

@Client.on_message(filters.private & filters.text & ~filters.command(list(_IGNORE_CMDS)))
async def text_handler(client, message: Message):
    uid  = message.from_user.id
    text = message.text.strip()
    sd   = _user_state.get(uid)
    if not sd: return
    state = sd.get("state")
    if state == "awaiting_prompt":
        _user_state.pop(uid, None)
        s = sd.get("settings", {})
        rem = await db.get_remaining_gens(uid)
        _user_state[uid] = {"state":"confirm","prompt":text,"settings":s}
        await _show_confirm(message, uid, text, s, rem)
    elif state == "awaiting_image_prompt":
        _user_state.pop(uid, None)
        sd["prompt"] = text
        await _start_generation(client, message, uid, sd)
    elif state == "awaiting_negative":
        _user_state.pop(uid, None)
        await db.update_user_setting(uid, "negative", text)
        await message.reply_text(
            f"<blockquote>✅ Negative prompt set.\n<code>{text[:200]}</code></blockquote>",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Settings", callback_data="menu_settings")
            ]])
        )
    elif state == "awaiting_watermark":
        _user_state.pop(uid, None)
        await db.update_user_setting(uid, "watermark", text)
        await message.reply_text(
            f"<blockquote>✅ Watermark: <code>{text[:50]}</code></blockquote>",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Settings", callback_data="menu_settings")
            ]])
        )
    elif state == "awaiting_seed":
        _user_state.pop(uid, None)
        try:
            seed = int(text)
            await db.update_user_setting(uid, "seed", seed)
            await message.reply_text(
                f"<blockquote>✅ Seed set to: <code>{seed}</code></blockquote>",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Settings", callback_data="menu_settings")
                ]])
            )
        except ValueError:
            await message.reply_text("<blockquote>❌ Invalid seed. Enter a number.</blockquote>")


# ── Show confirm + quick-adjust panel ────────────────────────

async def _show_confirm(target, uid, prompt, s, remaining):
    m  = Config.MODELS.get(s.get("model","zeroscope_xl"), {})
    st = s.get("style","realistic")
    res= s.get("resolution","576x320")
    dur= s.get("duration",3)
    enh= "✅" if s.get("enhance_prompt",True) else "❌"
    await target.reply_text(
        f"<blockquote>🎬 <b>Ready to Generate!</b>\n\n"
        f"📝 <b>Prompt:</b> {prompt[:200]}\n\n"
        f"🤖 <b>Model:</b> {m.get('icon','')} {m.get('name','?')}\n"
        f"🎨 <b>Style:</b> {st.title()}  📐 <b>Res:</b> {res}  ⏱ <b>Dur:</b> {dur}s\n"
        f"✨ <b>Enhance:</b> {enh}  ⚡ <b>Left:</b> {remaining}</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Generate Now!",  callback_data="do_generate"),
             InlineKeyboardButton("✏️ Edit Prompt",   callback_data="edit_prompt")],
            [InlineKeyboardButton("⚙️ Adjust Settings",callback_data="menu_settings")],
            [InlineKeyboardButton("❌ Cancel",          callback_data="cancel_gen")],
        ])
    )


# ── Queue + worker ────────────────────────────────────────────

async def _start_generation(client, target, uid: int, sd: dict):
    global _worker_running
    s         = sd.get("settings", {})
    prompt    = sd.get("prompt","")
    photo_fid = sd.get("photo_file_id")
    if photo_fid:
        s = dict(s)
        s["photo_file_id"] = photo_fid
    model_key  = s.get("model","zeroscope_xl")
    model_info = Config.MODELS.get(model_key, {})
    is_prem    = await db.has_premium_access(uid)
    # Priority: lower number = higher priority. Premium=0, free=1
    priority   = 0 if is_prem else 1

    await db.increment_gen_count(uid)
    qsize = _gen_queue.qsize()
    reply_target = target.message if hasattr(target,"message") else target
    status_msg = await reply_target.reply_text(
        f"<blockquote>⏳ <b>Queued!</b>\n\n"
        f"📍 Position: <b>#{qsize+1}</b>  {'💎 Priority' if is_prem else '🆓 Standard'}\n"
        f"🤖 <b>Model:</b> {model_info.get('name','?')}\n"
        f"📝 {prompt[:80]}{'…' if len(prompt)>80 else ''}\n\n"
        f"⏱ ~{(qsize+1)*40}–{(qsize+1)*120}s\n"
        f"<i>Auto-retry with fallback enabled 🔄</i></blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_job_{uid}")
        ]])
    )

    job = {
        "uid": uid, "prompt": prompt, "settings": s,
        "status_msg": status_msg, "client": client,
        "is_prem": is_prem, "cancelled": False,
        "enqueued_at": time.time(),
    }
    await _gen_queue.put((priority, time.time(), job))

    if not _worker_running:
        _worker_running = True
        asyncio.create_task(_queue_worker())


async def _queue_worker():
    global _worker_running
    while True:
        try:
            priority, ts, job = await asyncio.wait_for(_gen_queue.get(), timeout=60)
        except asyncio.TimeoutError:
            _worker_running = False
            return
        if not job.get("cancelled"):
            try:
                await _execute_job(job)
            except Exception as e:
                logger.error(f"Job error: {e}", exc_info=True)
                try:
                    await job["status_msg"].edit_text(
                        f"<blockquote>❌ Failed: {str(e)[:200]}\n\nTry /generate again.</blockquote>"
                    )
                except Exception: pass
        _gen_queue.task_done()
        await asyncio.sleep(1)


async def _execute_job(job: dict):
    uid        = job["uid"]
    client     = job["client"]
    status_msg = job["status_msg"]
    settings   = job["settings"]
    prompt     = job["prompt"]
    is_prem    = job["is_prem"]
    model_key  = settings.get("model","zeroscope_xl")
    model_info = Config.MODELS.get(model_key,{})
    enqueued   = job.get("enqueued_at", time.time())
    wait_secs  = int(time.time() - enqueued)

    await db.log_queue_entry(uid, model_key, "started", wait_secs)

    # Progress callback: updates the status message
    last_edit = [0.0]
    async def progress_cb(pct: int, label: str):
        now = time.time()
        if now - last_edit[0] < 4: return  # throttle edits
        last_edit[0] = now
        bar = progress_bar(pct)
        try:
            await status_msg.edit_text(
                f"<blockquote>🔄 <b>Generating…</b>\n\n"
                f"{bar}  <b>{pct}%</b>\n\n"
                f"⚙️ {label}\n"
                f"🤖 {model_info.get('name','?')}</blockquote>"
            )
        except Exception: pass

    video_path = None
    try:
        result = await generate_video(
            uid=uid,
            prompt=prompt,
            model_key=model_key,
            settings=settings,
            photo_download_fn=_make_photo_dl(client),
            progress_cb=progress_cb,
            is_premium=is_prem,
        )

        url         = result["url"]
        provider    = result["provider"]
        model_used  = result["model_used"]
        retry_count = result["retry_count"]
        from_cache  = result["from_cache"]
        elapsed     = result["elapsed"]

        await progress_cb(90, "Downloading video…")

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            video_path = tmp.name
        ok = await download_file(url, video_path)
        if not ok or not os.path.exists(video_path) or os.path.getsize(video_path) < 100:
            raise ValueError("Download failed or file is empty")

        remaining = await db.get_remaining_gens(uid)
        m_info    = Config.MODELS.get(model_used, model_info)
        res       = settings.get("resolution","?")
        dur       = settings.get("duration",3)
        retry_tag = f"  🔄 Retried ×{retry_count}" if retry_count else ""
        cache_tag = "  ♻️ Cached"                   if from_cache  else ""
        pip_tag   = "  🔥 Own Pipeline"              if provider == "own" else ""

        caption = (
            f"<blockquote>🎬 <b>Video Generated!</b>\n\n"
            f"📝 {prompt[:150]}{'…' if len(prompt)>150 else ''}\n\n"
            f"🤖 {m_info.get('icon','')} {m_info.get('name','?')}{pip_tag}\n"
            f"📐 {res}  ⏱ {dur}s  ⏳ {time_formatter(elapsed)}\n"
            f"⚡ Remaining: {remaining}{retry_tag}{cache_tag}\n\n"
            f"{'💎 Premium' if is_prem else '🆓 Free — /plan for unlimited'}\n"
            f"Powered by @BossHuBots</blockquote>"
        )
        sent = await client.send_video(
            chat_id=uid, video=video_path, caption=caption,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 Again",    callback_data="menu_generate"),
                 InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")],
                [InlineKeyboardButton("🏠 Menu",     callback_data="menu_main")],
            ])
        )
        file_id = sent.video.file_id if sent.video else ""
        await db.log_generation(
            uid=uid, prompt=prompt, model=model_key, status="success",
            video_url=url, file_id=file_id,
            duration_secs=int(elapsed), resolution=res,
            provider=provider, retry_count=retry_count
        )
        await db.log_queue_entry(uid, model_key, "success", wait_secs)
        try: await status_msg.delete()
        except Exception: pass

    except Exception as e:
        logger.error(f"Generation failed for {uid}: {e}", exc_info=True)
        await db.refund_gen(uid)
        await db.log_generation(uid=uid, prompt=prompt, model=model_key, status="failed")
        await db.log_queue_entry(uid, model_key, "failed", wait_secs)
        err = str(e)
        if "api" in err.lower() or "token" in err.lower():
            err = "API key error — contact admin."
        elif "timeout" in err.lower():
            err = "Timed out. Try a simpler prompt or different model."
        await status_msg.edit_text(
            f"<blockquote>❌ <b>Generation Failed</b>\n\n{err[:250]}\n\n"
            f"💡 Tips: shorter prompt · different model · check API keys\n\n"
            f"Contact @BossHuBots if this persists.</blockquote>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 Retry",    callback_data="menu_generate")],
                [InlineKeyboardButton("🏠 Main Menu",callback_data="menu_main")],
            ])
        )
    finally:
        await remove_file(video_path)


# ── Callback: do_generate ────────────────────────────────────

@Client.on_callback_query(filters.regex("^do_generate$"))
async def do_generate_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    sd  = _user_state.get(uid)
    if not sd:
        return await cb.answer("⚠️ Session expired. Use /generate again.", show_alert=True)
    if not await _can_generate(uid, cb.message):
        return await cb.answer()
    prompt = sd.get("prompt","")
    if not prompt:
        return await cb.answer("⚠️ No prompt. Type your prompt first.", show_alert=True)
    _user_state.pop(uid, None)
    await cb.answer("🚀 Starting generation!")
    await _start_generation(client, cb, uid, sd)


@Client.on_callback_query(filters.regex("^do_img2vid_auto$"))
async def do_img2vid_auto_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    sd  = _user_state.pop(uid, None)
    if not sd: return await cb.answer("Session expired.", show_alert=True)
    if not await _can_generate(uid, cb.message): return await cb.answer()
    sd["prompt"] = "smooth natural motion, gentle movement, high quality"
    await cb.answer("🎬 Starting!")
    await _start_generation(client, cb, uid, sd)


@Client.on_callback_query(filters.regex("^img2vid_add_prompt$"))
async def img2vid_add_prompt_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    sd  = _user_state.get(uid, {})
    sd["state"] = "awaiting_image_prompt"
    _user_state[uid] = sd
    await cb.message.edit_text(
        "<blockquote>✏️ <b>Enter Motion Prompt</b>\n\nDescribe the motion (e.g. 'slowly zoom in, slight breeze')</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_gen")
        ]])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^start_img2vid_last$"))
async def start_img2vid_last_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    sd  = _user_state.get(uid, {})
    if not sd.get("photo_file_id"):
        return await cb.answer("No image found.", show_alert=True)
    if not await _can_generate(uid, cb.message): return await cb.answer()
    sd["state"]  = "has_image"
    sd["settings"] = dict(sd.get("settings",{}))
    sd["settings"]["model"] = "stable_video"
    _user_state[uid] = sd
    await cb.message.edit_text(
        "<blockquote>✅ <b>Image ready!</b></blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ Auto Motion",  callback_data="do_img2vid_auto")],
            [InlineKeyboardButton("✏️ Add Prompt",  callback_data="img2vid_add_prompt")],
            [InlineKeyboardButton("❌ Cancel",       callback_data="cancel_gen")],
        ])
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^cancel_gen$"))
async def cancel_gen_cb(client, cb: CallbackQuery):
    _user_state.pop(cb.from_user.id, None)
    await cb.message.edit_text(
        "<blockquote>❌ Cancelled.</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu_main")
        ]])
    )
    await cb.answer("Cancelled")


@Client.on_callback_query(filters.regex("^edit_prompt$"))
async def edit_prompt_cb(client, cb: CallbackQuery):
    uid = cb.from_user.id
    sd  = _user_state.get(uid, {})
    sd["state"] = "awaiting_prompt"
    _user_state[uid] = sd
    await cb.message.edit_text(
        "<blockquote>✏️ Send new prompt:</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_gen")
        ]])
    )
    await cb.answer()
