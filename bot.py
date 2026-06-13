"""
BossHuBots AI Video Generator v2 — Main Entry Point
Starts: Pyrogram bot + Own REST API server (aiohttp) concurrently.
"""
import asyncio, logging, time, os
from pyrogram import Client, idle
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("BotLog.txt"),
        logging.StreamHandler(),
    ]
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Global bot instance (used by API server broadcast)
bot_instance: Client = None


class AIVideoBot(Client):
    def __init__(self):
        super().__init__(
            name="AIVideoBot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=200,
            plugins={"root": "plugins"},
            sleep_threshold=10,
        )

    async def start(self):
        await super().start()
        global bot_instance
        bot_instance = self

        from helper.database import db
        await db.ensure_indexes()

        me = await self.get_me()
        self.mention  = me.mention
        self.username = me.username

        logger.info(f"✅ Bot started: @{me.username}")
        logger.info(f"   Replicate: {'✅' if Config.REPLICATE_API_TOKEN else '❌'}")
        logger.info(f"   Luma AI:   {'✅' if Config.LUMA_API_KEY else '❌'}")
        logger.info(f"   Fal/Kling: {'✅' if Config.FAL_API_KEY else '❌'}")
        logger.info(f"   API server: {'✅ port ' + str(Config.API_PORT) if Config.API_ENABLED else '❌'}")

        await _register_commands(self)

        for aid in Config.ADMIN:
            try:
                await self.send_message(
                    aid,
                    f"<b>🎬 BossHuBots AI Video Generator v{Config.VERSION} started!</b>\n\n"
                    f"Bot: @{me.username}\n"
                    f"API keys:\n"
                    f"  Replicate: {'✅' if Config.REPLICATE_API_TOKEN else '❌ not set'}\n"
                    f"  Luma AI:   {'✅' if Config.LUMA_API_KEY else '❌ not set'}\n"
                    f"  Fal/Kling: {'✅' if Config.FAL_API_KEY else '❌ not set'}\n\n"
                    f"API Server: {'✅ :' + str(Config.API_PORT) if Config.API_ENABLED else '❌ disabled'}\n"
                    f"Use /admin for the admin panel."
                )
            except Exception: pass

        if Config.LOG_CHANNEL:
            try:
                import datetime
                await self.send_message(
                    Config.LOG_CHANNEL,
                    f"**🤖 Bot started!** v{Config.VERSION}\n"
                    f"{datetime.datetime.utcnow().strftime('%d %b %Y %H:%M UTC')}"
                )
            except Exception:
                logger.warning("Could not send startup log to LOG_CHANNEL")

    async def stop(self, *args):
        logger.info("Bot stopping…")
        for aid in Config.ADMIN:
            try: await self.send_message(aid, "<b>🛑 Bot stopped.</b>")
            except Exception: pass
        await super().stop()


async def _register_commands(bot: Client):
    from pyrogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat
    user_cmds = [
        BotCommand("start",    "🚀 Start / Main menu"),
        BotCommand("generate", "🎬 Generate a video"),
        BotCommand("img2vid",  "🖼️ Image to video"),
        BotCommand("settings", "⚙️ My settings"),
        BotCommand("stats",    "📊 My stats"),
        BotCommand("history",  "📜 My history"),
        BotCommand("plan",     "💎 My plan & limits"),
        BotCommand("help",     "❓ Help"),
        BotCommand("about",    "ℹ️ About bot"),
    ]
    admin_cmds = user_cmds + [
        BotCommand("admin",            "🛠️ Admin panel"),
        BotCommand("broadcast",        "📢 Broadcast"),
        BotCommand("ban",              "🚫 Ban user"),
        BotCommand("unban",            "✅ Unban user"),
        BotCommand("add_premium",      "💎 Add premium"),
        BotCommand("remove_premium",   "❌ Remove premium"),
        BotCommand("add_fsub",         "📢 Add force-sub"),
        BotCommand("remove_fsub",      "🗑 Remove force-sub"),
        BotCommand("list_fsub",        "📋 List force-sub"),
        BotCommand("maintenance_on",   "🔧 Maintenance ON"),
        BotCommand("maintenance_off",  "✅ Maintenance OFF"),
        BotCommand("stats_full",       "📊 Full stats"),
        BotCommand("create_api_token", "🔑 Create API token"),
        BotCommand("list_api_tokens",  "📋 List API tokens"),
        BotCommand("revoke_api_token", "🗑 Revoke API token"),
        BotCommand("logs",             "📥 Download logs"),
        BotCommand("restart",          "🔄 Restart bot"),
    ]
    try:
        await bot.set_bot_commands(user_cmds, scope=BotCommandScopeAllPrivateChats())
        for aid in Config.ADMIN:
            try: await bot.set_bot_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=aid))
            except Exception: pass
        logger.info("✅ Commands registered")
    except Exception as e:
        logger.warning(f"Command registration failed: {e}")


async def main():
    bot = AIVideoBot()

    # Start API server in parallel
    api_runner = None
    if Config.API_ENABLED:
        from api_server import start_api_server
        api_runner = await start_api_server()

    await bot.start()
    await idle()
    await bot.stop()

    if api_runner:
        await api_runner.cleanup()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Stopped.")
    finally:
        loop.close()
