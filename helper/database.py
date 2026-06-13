"""
Extended MongoDB database layer — users, generations, premium, fsub,
bot settings, API tokens, generation queue stats, config store.
"""
import motor.motor_asyncio, datetime, secrets, hashlib
from config import Config


class Database:
    def __init__(self, uri, db_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db           = self._client[db_name]
        self.users        = self.db.users
        self.gens         = self.db.generations
        self.premium      = self.db.premium
        self.fsub         = self.db.fsub_channels
        self.settings_col = self.db.bot_settings
        self.api_tokens   = self.db.api_tokens
        self.gen_queue_log= self.db.queue_log

    # ── Indexes (call once on startup) ────────────────────────
    async def ensure_indexes(self):
        await self.users.create_index("_id")
        await self.gens.create_index([("user_id", 1), ("created_at", -1)])
        await self.gens.create_index("status")
        await self.api_tokens.create_index("token", unique=True)

    # ─────────────── USERS ────────────────────────────────────

    def _new_user(self, uid):
        return {
            "_id": int(uid),
            "join_date": datetime.datetime.utcnow(),
            "daily_gens": 0,
            "daily_reset": datetime.datetime.utcnow(),
            "total_gens": 0,
            "ban_status": {"is_banned": False, "reason": ""},
            "settings": {
                "model": "zeroscope_xl",
                "style": "realistic",
                "resolution": "576x320",
                "duration": 3,
                "aspect": "16:9",
                "negative": Config.NEGATIVE_DEFAULT,
                "watermark": "",
                "enhance_prompt": True,
                "notifications": True,
                "quality": "high",
                "seed": -1,
            },
        }

    async def add_user(self, uid):
        if not await self.is_user_exist(uid):
            await self.users.insert_one(self._new_user(uid))

    async def is_user_exist(self, uid):
        return bool(await self.users.find_one({"_id": int(uid)}))

    async def get_user(self, uid):
        return await self.users.find_one({"_id": int(uid)})

    async def update_user(self, uid, data: dict):
        await self.users.update_one({"_id": int(uid)}, {"$set": data}, upsert=True)

    async def update_user_setting(self, uid, key, value):
        await self.users.update_one(
            {"_id": int(uid)},
            {"$set": {f"settings.{key}": value}},
            upsert=True
        )

    async def get_user_setting(self, uid, key, default=None):
        u = await self.get_user(uid)
        if not u:
            return default
        return u.get("settings", {}).get(key, default)

    async def total_users_count(self):
        return await self.users.count_documents({})

    async def get_all_users(self):
        return self.users.find({})

    async def delete_user(self, uid):
        await self.users.delete_one({"_id": int(uid)})

    async def get_recent_users(self, limit=10):
        cursor = self.users.find({}).sort("join_date", -1).limit(limit)
        return await cursor.to_list(length=limit)

    # ─────────────── DAILY LIMITS ─────────────────────────────

    async def get_remaining_gens(self, uid) -> int:
        u = await self.get_user(uid)
        if not u:
            return Config.FREE_DAILY_GENS
        now = datetime.datetime.utcnow()
        reset = u.get("daily_reset", now)
        if isinstance(reset, datetime.datetime) and (now - reset).total_seconds() > 86400:
            await self.update_user(uid, {"daily_gens": 0, "daily_reset": now})
            return await self._limit(uid)
        used  = u.get("daily_gens", 0)
        limit = await self._limit(uid)
        return max(0, limit - used)

    async def _limit(self, uid) -> int:
        return Config.PREMIUM_DAILY_GENS if await self.has_premium_access(uid) else Config.FREE_DAILY_GENS

    async def increment_gen_count(self, uid):
        await self.users.update_one(
            {"_id": int(uid)},
            {"$inc": {"daily_gens": 1, "total_gens": 1}},
            upsert=True
        )

    async def refund_gen(self, uid):
        await self.users.update_one(
            {"_id": int(uid)},
            {"$inc": {"daily_gens": -1, "total_gens": -1}},
        )

    # ─────────────── GENERATION HISTORY ──────────────────────

    async def log_generation(self, uid, prompt, model, status,
                              video_url="", file_id="", duration_secs=0,
                              resolution="", provider="", retry_count=0):
        await self.gens.insert_one({
            "user_id": int(uid),
            "prompt": prompt,
            "model": model,
            "provider": provider,
            "status": status,
            "video_url": video_url,
            "file_id": file_id,
            "duration_secs": duration_secs,
            "resolution": resolution,
            "retry_count": retry_count,
            "created_at": datetime.datetime.utcnow(),
        })

    async def get_user_history(self, uid, limit=10):
        cursor = self.gens.find(
            {"user_id": int(uid), "status": "success"}
        ).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def total_generations_count(self):
        return await self.gens.count_documents({})

    async def today_generations_count(self):
        today = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return await self.gens.count_documents({"created_at": {"$gte": today}})

    async def failed_generations_count(self):
        return await self.gens.count_documents({"status": "failed"})

    async def get_generation_stats_by_model(self):
        pipeline = [
            {"$group": {"_id": "$model", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        cursor = self.gens.aggregate(pipeline)
        return await cursor.to_list(length=20)

    async def get_generation_stats_by_day(self, days=7):
        since = datetime.datetime.utcnow() - datetime.timedelta(days=days)
        pipeline = [
            {"$match": {"created_at": {"$gte": since}, "status": "success"}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]
        cursor = self.gens.aggregate(pipeline)
        return await cursor.to_list(length=days + 2)

    # ─────────────── BAN ──────────────────────────────────────

    async def ban_user(self, uid, reason=""):
        await self.update_user(uid, {"ban_status": {"is_banned": True, "reason": reason}})

    async def unban_user(self, uid):
        await self.update_user(uid, {"ban_status": {"is_banned": False, "reason": ""}})

    async def is_banned(self, uid) -> bool:
        u = await self.get_user(uid)
        return u.get("ban_status", {}).get("is_banned", False) if u else False

    async def get_ban_reason(self, uid) -> str:
        u = await self.get_user(uid)
        return u.get("ban_status", {}).get("reason", "") if u else ""

    async def get_all_banned(self):
        return self.users.find({"ban_status.is_banned": True})

    # ─────────────── PREMIUM ──────────────────────────────────

    async def add_premium(self, uid, days: int, plan: str = "Premium"):
        expiry = datetime.datetime.utcnow() + datetime.timedelta(days=days)
        await self.premium.update_one(
            {"_id": int(uid)},
            {"$set": {"expiry": expiry, "plan": plan, "added_on": datetime.datetime.utcnow()}},
            upsert=True
        )

    async def remove_premium(self, uid):
        await self.premium.delete_one({"_id": int(uid)})

    async def has_premium_access(self, uid) -> bool:
        doc = await self.premium.find_one({"_id": int(uid)})
        if not doc:
            return False
        expiry = doc.get("expiry")
        if expiry and datetime.datetime.utcnow() <= expiry:
            return True
        await self.remove_premium(uid)
        return False

    async def get_premium_info(self, uid):
        return await self.premium.find_one({"_id": int(uid)})

    async def total_premium_count(self):
        return await self.premium.count_documents(
            {"expiry": {"$gt": datetime.datetime.utcnow()}}
        )

    async def get_all_premium(self):
        return self.premium.find({"expiry": {"$gt": datetime.datetime.utcnow()}})

    # ─────────────── FORCE-SUB ────────────────────────────────

    async def add_fsub_channel(self, channel_id, invite_link, title) -> bool:
        exists = await self.fsub.find_one({"channel_id": channel_id})
        if exists:
            await self.fsub.update_one(
                {"channel_id": channel_id},
                {"$set": {"invite_link": invite_link, "title": title}}
            )
            return False
        await self.fsub.insert_one({
            "channel_id": channel_id,
            "invite_link": invite_link,
            "title": title,
            "added_at": datetime.datetime.utcnow(),
        })
        return True

    async def remove_fsub_channel(self, channel_id) -> bool:
        r = await self.fsub.delete_one({"channel_id": channel_id})
        return r.deleted_count > 0

    async def get_all_fsub_channels(self) -> list:
        out = []
        async for doc in self.fsub.find({}).sort("added_at", 1):
            out.append({"channel_id": doc["channel_id"],
                        "invite_link": doc.get("invite_link",""),
                        "title": doc.get("title", str(doc["channel_id"]))})
        return out

    async def clear_fsub_channels(self):
        await self.fsub.delete_many({})

    # ─────────────── BOT SETTINGS ────────────────────────────

    async def set_setting(self, key, value):
        await self.settings_col.update_one(
            {"_id": "global"}, {"$set": {key: value}}, upsert=True
        )

    async def get_setting(self, key, default=None):
        doc = await self.settings_col.find_one({"_id": "global"})
        return doc.get(key, default) if doc else default

    async def set_maintenance(self, enabled: bool, msg: str = ""):
        await self.set_setting("maintenance", enabled)
        await self.set_setting("maintenance_msg", msg)

    async def get_maintenance(self):
        doc = await self.settings_col.find_one({"_id": "global"})
        if doc:
            return doc.get("maintenance", False), doc.get("maintenance_msg", "")
        return False, ""

    async def get_all_settings(self) -> dict:
        doc = await self.settings_col.find_one({"_id": "global"})
        if doc:
            doc.pop("_id", None)
        return doc or {}

    # ─────────────── API TOKENS (own API auth) ────────────────

    async def create_api_token(self, label: str, created_by: int, permissions: list = None) -> str:
        token = secrets.token_hex(32)
        hashed = hashlib.sha256(token.encode()).hexdigest()
        await self.api_tokens.insert_one({
            "token_hash": hashed,
            "label": label,
            "created_by": int(created_by),
            "permissions": permissions or ["read"],
            "created_at": datetime.datetime.utcnow(),
            "last_used": None,
            "request_count": 0,
            "active": True,
        })
        return token

    async def validate_api_token(self, token: str) -> dict | None:
        hashed = hashlib.sha256(token.encode()).hexdigest()
        doc = await self.api_tokens.find_one({"token_hash": hashed, "active": True})
        if doc:
            await self.api_tokens.update_one(
                {"token_hash": hashed},
                {"$set": {"last_used": datetime.datetime.utcnow()},
                 "$inc": {"request_count": 1}}
            )
        return doc

    async def list_api_tokens(self) -> list:
        cursor = self.api_tokens.find({"active": True}).sort("created_at", -1)
        docs = await cursor.to_list(length=50)
        for d in docs:
            d.pop("token_hash", None)
            d.pop("_id", None)
        return docs

    async def revoke_api_token(self, label: str) -> bool:
        r = await self.api_tokens.update_one(
            {"label": label},
            {"$set": {"active": False}}
        )
        return r.modified_count > 0

    # ─────────────── QUEUE LOG ───────────────────────────────

    async def log_queue_entry(self, uid, model, status, wait_secs=0):
        await self.gen_queue_log.insert_one({
            "user_id": int(uid),
            "model": model,
            "status": status,
            "wait_secs": wait_secs,
            "timestamp": datetime.datetime.utcnow(),
        })

    async def avg_queue_wait(self) -> float:
        pipeline = [
            {"$match": {"wait_secs": {"$gt": 0}}},
            {"$group": {"_id": None, "avg": {"$avg": "$wait_secs"}}},
        ]
        cursor = self.gen_queue_log.aggregate(pipeline)
        res = await cursor.to_list(length=1)
        return res[0]["avg"] if res else 0.0


db = Database(Config.DB_URL, Config.DB_NAME)
