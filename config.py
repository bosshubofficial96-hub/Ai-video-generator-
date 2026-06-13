import os, re, time, secrets
from dotenv import load_dotenv
load_dotenv()

id_pattern = re.compile(r'^-?\d+$')

class Config:
    # ── Core Telegram ─────────────────────────────────────────
    API_ID        = os.environ.get("API_ID", "27806628")
    API_HASH      = os.environ.get("API_HASH", "25d88301e886b82826a525b7cf52e090")
    BOT_TOKEN     = os.environ.get("BOT_TOKEN", "8475837125:AAFQn_RKsvTttpKS_bN6H10_EuopPrG9S5k")

    # ── Database ──────────────────────────────────────────────
    DB_URL        = os.environ.get("DB_URL", "mongodb+srv://Bosshub:JMaff0WvazwNxKky@cluster0.l0xcoc1.mongodb.net/?appName=Cluster0")
    DB_NAME       = os.environ.get("DB_NAME", "AIVideoGenBot")

    # ── Admin & Logging ───────────────────────────────────────
    ADMIN         = [int(a) for a in os.environ.get("ADMIN", "8525952693").split() if id_pattern.match(a)]
    LOG_CHANNEL   = int(os.environ.get("LOG_CHANNEL", "0") or "0")

    # ── AI Provider APIs ──────────────────────────────────────
    REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "key_0085d1b57a4120051c822e00f70461f3e639b9c742757117b7463c5e1e73e5bc21feed5e5a4eae2521f67480567b9cc031f13f47d279e9c64ccca4b87bd132e3")
    LUMA_API_KEY        = os.environ.get("LUMA_API_KEY", "")
    FAL_API_KEY         = os.environ.get("FAL_API_KEY", "")
    STABILITY_API_KEY   = os.environ.get("STABILITY_API_KEY", "")
    RUNWAY_API_KEY      = os.environ.get("RUNWAY_API_KEY", "")

    # ── Own Web API Server ────────────────────────────────────
    API_PORT        = int(os.environ.get("API_PORT", "8080"))
    API_SECRET_KEY  = os.environ.get("API_SECRET_KEY", secrets.token_hex(32))
    API_ENABLED     = os.environ.get("API_ENABLED", "true").lower() == "true"
    API_RATE_LIMIT  = int(os.environ.get("API_RATE_LIMIT", "60"))   # reqs/min

    # ── Force Subscribe ───────────────────────────────────────
    try:    FORCE_SUB  = int(os.environ.get("FORCE_SUB",  "0"))
    except: FORCE_SUB  = os.environ.get("FORCE_SUB",  "")
    try:    FORCE_SUB2 = int(os.environ.get("FORCE_SUB2", "0"))
    except: FORCE_SUB2 = os.environ.get("FORCE_SUB2", "")
    FORCE_SUB_IMAGE = os.environ.get("FORCE_SUB_IMAGE", "")

    # ── Bot Identity ──────────────────────────────────────────
    BOT_NAME        = "BossHuBots AI Video Generator"
    VERSION         = "2.0.0"
    SUPPORT_CHAT    = os.environ.get("SUPPORT_CHAT",    "https://t.me/BossHuBots")
    UPDATES_CHANNEL = os.environ.get("UPDATES_CHANNEL", "https://t.me/BossHuBots")
    BOT_UPTIME      = time.time()

    # ── Limits ────────────────────────────────────────────────
    FREE_DAILY_GENS     = int(os.environ.get("FREE_DAILY_GENS",    "3"))
    PREMIUM_DAILY_GENS  = int(os.environ.get("PREMIUM_DAILY_GENS", "50"))
    MAX_QUEUE_SIZE      = int(os.environ.get("MAX_QUEUE_SIZE",      "20"))
    GEN_TIMEOUT_SECS    = int(os.environ.get("GEN_TIMEOUT_SECS",   "300"))
    MAX_RETRIES         = int(os.environ.get("MAX_RETRIES",         "3"))
    RETRY_DELAY_BASE    = float(os.environ.get("RETRY_DELAY_BASE",  "5"))

    # ── AI Models registry ────────────────────────────────────
    MODELS = {
        "zeroscope_xl": {
            "name": "Zeroscope XL", "icon": "🎬", "provider": "replicate",
            "model_id": "anotherjesse/zeroscope-v2-xl:9f747673945c62801b13b84701c783929c0ee784e4748ec062204894dda1a351",
            "type": "text2video",
            "resolutions": ["576x320", "1024x576"],
            "durations": [2, 3, 4], "free": True,
            "description": "Fast, high-quality text-to-video",
        },
        "animatediff": {
            "name": "AnimateDiff", "icon": "✨", "provider": "replicate",
            "model_id": "lucataco/animate-diff:beecf59c4aee8d81bf04f0381033dfa10dc16e845b4ae00d281e2fa377e48a9f",
            "type": "text2video",
            "resolutions": ["512x512", "768x512"],
            "durations": [2, 3, 4], "free": True,
            "description": "Smooth animated sequences",
        },
        "stable_video": {
            "name": "Stable Video Diffusion", "icon": "🖼️", "provider": "replicate",
            "model_id": "stability-ai/stable-video-diffusion:3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438",
            "type": "img2video",
            "resolutions": ["1024x576", "576x1024"],
            "durations": [3, 4], "free": True,
            "description": "Animate images into video",
        },
        "hotshot_xl": {
            "name": "Hotshot XL (GIF)", "icon": "🌀", "provider": "replicate",
            "model_id": "lucataco/hotshot-xl:78b3a6257e16e4b241245d65c8b2b81ea2e1ff7ed4c55306b511509ddbfd327a",
            "type": "text2gif",
            "resolutions": ["512x512", "672x384"],
            "durations": [1, 2], "free": True,
            "description": "Animated GIF generation",
        },
        "luma_dream": {
            "name": "Luma Dream Machine", "icon": "💫", "provider": "luma",
            "model_id": "dream-machine",
            "type": "text2video",
            "resolutions": ["1280x720", "720x1280", "960x540"],
            "durations": [5], "free": False,
            "description": "Cinematic quality (Luma API key)",
        },
        "fal_kling": {
            "name": "Kling AI", "icon": "⚡", "provider": "fal",
            "model_id": "fal-ai/kling-video/v1/standard/text-to-video",
            "type": "text2video",
            "resolutions": ["1280x720", "720x1280"],
            "durations": [5, 10], "free": False,
            "description": "Ultra-realistic (Fal API key)",
        },
        "own_pipeline": {
            "name": "BossHuBots Pipeline", "icon": "🔥", "provider": "own",
            "model_id": "own_txt2img2vid",
            "type": "text2video",
            "resolutions": ["512x512", "768x512"],
            "durations": [2, 3], "free": True,
            "description": "Our own SD→SVD pipeline (no extra key)",
        },
    }

    STYLE_PRESETS = {
        "realistic":  "photorealistic, high quality, 8K HDR, sharp detail",
        "cinematic":  "cinematic, film grain, dramatic lighting, anamorphic lens, movie scene",
        "anime":      "anime style, vibrant colors, cel-shaded, Studio Ghibli, detailed",
        "cartoon":    "cartoon style, colorful, animated, flat design, playful",
        "abstract":   "abstract art, surreal, psychedelic, artistic, fluid shapes",
        "dark":       "dark atmosphere, moody noir, dramatic shadows, gothic, brooding",
        "nature":     "nature documentary, 8K wildlife, lush colors, peaceful, BBC quality",
        "scifi":      "sci-fi futuristic, neon lights, cyberpunk, holographic, blade runner",
    }

    PROMPT_ENHANCERS = [
        "highly detailed", "4K", "smooth motion", "professional quality",
        "sharp focus", "vivid colors", "masterpiece",
    ]

    NEGATIVE_DEFAULT = (
        "blurry, low quality, distorted, ugly, deformed, noisy, watermark, "
        "text overlay, bad anatomy, duplicate frames, flickering"
    )
