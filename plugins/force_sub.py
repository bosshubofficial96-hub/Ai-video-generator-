from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from config import Config
from helper.database import db

async def _channels(client) -> list:
    chs = await db.get_all_fsub_channels()
    if chs: return chs
    legacy = []
    for ref in [Config.FORCE_SUB, Config.FORCE_SUB2]:
        if ref and str(ref) not in ("0",""):
            try:
                chat = await client.get_chat(ref)
                try: link = chat.invite_link or await client.export_chat_invite_link(chat.id)
                except Exception: link = f"https://t.me/{chat.username}" if chat.username else ""
                legacy.append({"channel_id": chat.id, "invite_link": link, "title": chat.title or str(chat.id)})
            except Exception: pass
    return legacy

async def not_subscribed(_, client, message: Message) -> bool:
    if not message.from_user: return False
    uid = message.from_user.id
    if uid in Config.ADMIN: return False
    chs = await _channels(client)
    if not chs: return False
    for ch in chs:
        try:
            member = await client.get_chat_member(ch["channel_id"], uid)
            if member.status not in [enums.ChatMemberStatus.MEMBER,
                                      enums.ChatMemberStatus.ADMINISTRATOR,
                                      enums.ChatMemberStatus.OWNER]:
                return True
        except UserNotParticipant: return True
        except Exception: continue
    return False

async def send_fsub_msg(client, message: Message):
    chs  = await _channels(client)
    btns = [[InlineKeyboardButton(f"📢 Join {ch['title']}", url=ch["invite_link"])]
             for ch in chs if ch.get("invite_link")]
    if not btns: btns = [[InlineKeyboardButton("📢 Join Channel", url=Config.SUPPORT_CHAT)]]
    btns.append([InlineKeyboardButton("✅ I Joined — Verify", callback_data="fsub_check")])
    try:
        if Config.FORCE_SUB_IMAGE:
            return await message.reply_photo(
                Config.FORCE_SUB_IMAGE,
                caption="<blockquote>🔒 <b>Join required channels to use this bot.</b></blockquote>",
                reply_markup=InlineKeyboardMarkup(btns)
            )
    except Exception: pass
    await message.reply_text(
        "<blockquote>🔒 <b>Join required channels to use this bot!</b></blockquote>",
        reply_markup=InlineKeyboardMarkup(btns)
    )

@Client.on_message(filters.private & filters.create(not_subscribed))
async def fsub_handler(client, message: Message):
    await send_fsub_msg(client, message)
