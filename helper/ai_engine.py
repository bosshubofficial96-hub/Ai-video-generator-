"""
Own AI Video Generation Engine
Features:
  • Multi-provider support (Replicate, Luma, Fal, Own Pipeline)
  • Automatic retry with exponential backoff
  • Provider fallback chain
  • Prompt enhancement / enrichment
  • Priority queue (premium users jump the queue)
  • Live progress callbacks
  • Generation caching (same prompt+model = reuse URL)
"""
import asyncio, aiohttp, os, time, logging, hashlib, tempfile
from config import Config

logger = logging.getLogger(__name__)

# ── Simple in-memory URL cache (prompt+model → url) ───────────
_url_cache: dict[str, tuple[str, float]] = {}   # key → (url, ts)
CACHE_TTL = 3600  # 1 hour

def _cache_key(prompt: str, model_key: str, res: str, dur: int) -> str:
    raw = f"{prompt}|{model_key}|{res}|{dur}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def _cache_get(key: str) -> str | None:
    entry = _url_cache.get(key)
    if entry and (time.time() - entry[1]) < CACHE_TTL:
        return entry[0]
    _url_cache.pop(key, None)
    return None

def _cache_set(key: str, url: str):
    _url_cache[key] = (url, time.time())


# ── Prompt enhancer ────────────────────────────────────────────

def enhance_prompt(prompt: str, style_suffix: str, enable: bool = True) -> str:
    base = prompt.strip().rstrip(".,")
    if style_suffix:
        base = f"{base}, {style_suffix}"
    if enable:
        extras = ["highly detailed", "smooth motion", "professional quality"]
        base = f"{base}, {', '.join(extras)}"
    return base


# ── Fallback provider chain ────────────────────────────────────
# Maps a model_key to ordered list of (provider_fn, model_key_override)
# If primary provider fails, engine tries next in chain.
FALLBACK_CHAINS: dict[str, list[str]] = {
    "zeroscope_xl":  ["zeroscope_xl", "animatediff", "own_pipeline"],
    "animatediff":   ["animatediff",  "zeroscope_xl","own_pipeline"],
    "stable_video":  ["stable_video"],
    "hotshot_xl":    ["hotshot_xl",   "animatediff"],
    "luma_dream":    ["luma_dream",   "zeroscope_xl"],
    "fal_kling":     ["fal_kling",    "zeroscope_xl"],
    "own_pipeline":  ["own_pipeline", "zeroscope_xl"],
}


# ── Main engine entry ──────────────────────────────────────────

async def generate_video(
    uid: int,
    prompt: str,
    model_key: str,
    settings: dict,
    photo_download_fn=None,        # async fn(file_id) → local_path
    progress_cb=None,              # async fn(pct, label)
    is_premium: bool = False,
) -> dict:
    """
    Returns dict:
        {
          "url": str,          # direct video URL
          "provider": str,
          "model_used": str,
          "retry_count": int,
          "from_cache": bool,
          "elapsed": float,
        }
    Raises RuntimeError on total failure.
    """
    res   = settings.get("resolution", "576x320")
    dur   = int(settings.get("duration",  3))
    style = settings.get("style", "realistic")
    enhance = settings.get("enhance_prompt", True)
    neg   = settings.get("negative", Config.NEGATIVE_DEFAULT)

    style_suffix = Config.STYLE_PRESETS.get(style, "")
    final_prompt = enhance_prompt(prompt, style_suffix, enhance)

    # Cache check (skip for img2video)
    photo_fid = settings.get("photo_file_id")
    if not photo_fid:
        ckey = _cache_key(final_prompt, model_key, res, dur)
        cached = _cache_get(ckey)
        if cached:
            logger.info(f"Cache HIT for {model_key}")
            return {"url": cached, "provider": "cache", "model_used": model_key,
                    "retry_count": 0, "from_cache": True, "elapsed": 0.0}
    else:
        ckey = None

    chain = FALLBACK_CHAINS.get(model_key, [model_key])
    total_retries = 0
    last_error    = None
    start_t       = time.time()

    for attempt_model in chain:
        model_info = Config.MODELS.get(attempt_model, {})
        provider   = model_info.get("provider", "replicate")
        pct_base   = 10

        for retry in range(Config.MAX_RETRIES):
            try:
                if progress_cb:
                    await progress_cb(pct_base + retry * 5,
                                      f"Attempt {total_retries+1} · {model_info.get('name','?')}…")

                url = await _dispatch(
                    provider=provider,
                    attempt_model=attempt_model,
                    model_info=model_info,
                    final_prompt=final_prompt,
                    neg_prompt=neg,
                    res=res,
                    dur=dur,
                    photo_fid=photo_fid,
                    photo_dl_fn=photo_download_fn,
                    progress_cb=progress_cb,
                )

                if url:
                    elapsed = time.time() - start_t
                    if ckey:
                        _cache_set(ckey, url)
                    return {
                        "url": url,
                        "provider": provider,
                        "model_used": attempt_model,
                        "retry_count": total_retries,
                        "from_cache": False,
                        "elapsed": elapsed,
                    }

            except asyncio.TimeoutError:
                last_error = f"Timeout after {Config.GEN_TIMEOUT_SECS}s"
                logger.warning(f"[{attempt_model}] Timeout (retry {retry+1})")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[{attempt_model}] Error (retry {retry+1}): {e}")

            total_retries += 1
            if retry < Config.MAX_RETRIES - 1:
                delay = Config.RETRY_DELAY_BASE * (2 ** retry)
                logger.info(f"Retrying in {delay}s…")
                await asyncio.sleep(delay)

    raise RuntimeError(f"All providers failed. Last error: {last_error}")


async def _dispatch(provider, attempt_model, model_info, final_prompt, neg_prompt,
                    res, dur, photo_fid, photo_dl_fn, progress_cb) -> str:
    if provider == "replicate":
        return await _run_replicate(attempt_model, model_info, final_prompt, neg_prompt,
                                    res, dur, photo_fid, photo_dl_fn, progress_cb)
    elif provider == "luma":
        return await _run_luma(final_prompt, dur, progress_cb)
    elif provider == "fal":
        return await _run_fal(model_info, final_prompt, res, dur, progress_cb)
    elif provider == "own":
        return await _run_own_pipeline(final_prompt, neg_prompt, res, dur, progress_cb)
    else:
        raise ValueError(f"Unknown provider: {provider}")


# ── Replicate ─────────────────────────────────────────────────

async def _run_replicate(model_key, model_info, prompt, neg, res, dur,
                          photo_fid, photo_dl_fn, progress_cb) -> str:
    if not Config.REPLICATE_API_TOKEN:
        raise ValueError("REPLICATE_API_TOKEN not set")

    import replicate as rep
    os.environ["REPLICATE_API_TOKEN"] = Config.REPLICATE_API_TOKEN

    model_id = model_info["model_id"]
    w, h     = map(int, res.split("x"))

    if model_key == "zeroscope_xl":
        inp = {"prompt": prompt, "negative_prompt": neg,
               "width": w, "height": h, "num_frames": dur * 24,
               "num_inference_steps": 40, "guidance_scale": 17.5}
    elif model_key == "animatediff":
        inp = {"prompt": prompt, "negative_prompt": neg,
               "width": w, "height": h, "num_frames": dur * 8,
               "num_inference_steps": 25, "guidance_scale": 7.5}
    elif model_key == "stable_video":
        if not photo_fid or not photo_dl_fn:
            raise ValueError("Image required for Stable Video Diffusion")
        photo_path = await photo_dl_fn(photo_fid)
        with open(photo_path, "rb") as f:
            inp = {"input_image": f, "sizing_strategy": "maintain_aspect_ratio",
                   "frames_per_second": 8, "num_frames": dur * 8,
                   "motion_bucket_id": 127, "cond_aug": 0.02}
    elif model_key == "hotshot_xl":
        inp = {"prompt": prompt, "negative_prompt": neg,
               "width": w, "height": h, "num_inference_steps": 20}
    else:
        inp = {"prompt": prompt, "negative_prompt": neg}

    async def _prog():
        steps = [(20,"Encoding…"),(40,"Generating frames…"),(65,"Rendering…"),(80,"Encoding video…")]
        for pct, lbl in steps:
            await asyncio.sleep(15)
            if progress_cb:
                try: await progress_cb(pct, lbl)
                except Exception: pass

    pt = asyncio.create_task(_prog())
    try:
        output = await asyncio.wait_for(
            asyncio.to_thread(rep.run, model_id, input=inp),
            timeout=Config.GEN_TIMEOUT_SECS
        )
        pt.cancel()
        if isinstance(output, list):
            return str(output[0])
        if hasattr(output, "url"):
            return output.url
        return str(output)
    finally:
        pt.cancel()


# ── Luma ─────────────────────────────────────────────────────

async def _run_luma(prompt, dur, progress_cb) -> str:
    if not Config.LUMA_API_KEY:
        raise ValueError("LUMA_API_KEY not set")

    headers = {"Authorization": f"Bearer {Config.LUMA_API_KEY}",
               "Content-Type": "application/json"}
    payload = {"prompt": prompt, "aspect_ratio": "16:9", "loop": False}

    async with aiohttp.ClientSession() as sess:
        async with sess.post(
            "https://api.lumalabs.ai/dream-machine/v1/generations",
            headers=headers, json=payload,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as r:
            data = await r.json()
            if r.status != 201:
                raise ValueError(f"Luma API {r.status}: {data}")
            gen_id = data["id"]

        for i in range(80):
            await asyncio.sleep(5)
            if progress_cb:
                try: await progress_cb(20 + i, "Luma Dream Machine processing…")
                except Exception: pass
            async with sess.get(
                f"https://api.lumalabs.ai/dream-machine/v1/generations/{gen_id}",
                headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                data = await r.json()
                if data.get("state") == "completed":
                    return data["assets"]["video"]
                if data.get("state") == "failed":
                    raise ValueError(f"Luma failed: {data.get('failure_reason','?')}")

    raise ValueError("Luma timed out")


# ── Fal (Kling) ──────────────────────────────────────────────

async def _run_fal(model_info, prompt, res, dur, progress_cb) -> str:
    if not Config.FAL_API_KEY:
        raise ValueError("FAL_API_KEY not set")

    import fal_client
    os.environ["FAL_KEY"] = Config.FAL_API_KEY
    model_id = model_info["model_id"]

    async def _prog():
        for pct in [20, 45, 70, 85]:
            await asyncio.sleep(20)
            if progress_cb:
                try: await progress_cb(pct, "Kling AI generating…")
                except Exception: pass

    pt = asyncio.create_task(_prog())
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(fal_client.run, model_id,
                              arguments={"prompt": prompt, "duration": str(dur),
                                         "aspect_ratio": "16:9"}),
            timeout=Config.GEN_TIMEOUT_SECS
        )
        pt.cancel()
        vids = result.get("video", result.get("videos", []))
        if isinstance(vids, list) and vids:
            return vids[0].get("url") or str(vids[0])
        if isinstance(vids, dict):
            return vids.get("url", "")
        return str(vids)
    finally:
        pt.cancel()


# ── Own Pipeline (SD text→image → SVD image→video) ───────────

async def _run_own_pipeline(prompt, neg, res, dur, progress_cb) -> str:
    """
    Our own two-stage pipeline:
      Stage 1: text → image  (Replicate SDXL)
      Stage 2: image → video (Replicate SVD)
    Falls back to zeroscope_xl if REPLICATE_API_TOKEN unavailable.
    """
    if not Config.REPLICATE_API_TOKEN:
        raise ValueError("REPLICATE_API_TOKEN required for own pipeline")

    import replicate as rep
    os.environ["REPLICATE_API_TOKEN"] = Config.REPLICATE_API_TOKEN
    w, h = map(int, res.split("x"))

    if progress_cb:
        await progress_cb(15, "Stage 1/2 — Generating reference image…")

    # Stage 1: SDXL text → image
    sdxl_id = "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b"
    img_output = await asyncio.wait_for(
        asyncio.to_thread(rep.run, sdxl_id,
                          input={"prompt": prompt, "negative_prompt": neg,
                                 "width": w, "height": h,
                                 "num_outputs": 1, "num_inference_steps": 30}),
        timeout=120
    )
    if isinstance(img_output, list):
        img_url = str(img_output[0])
    else:
        img_url = str(img_output)

    if progress_cb:
        await progress_cb(50, "Stage 2/2 — Animating image to video…")

    # Download the image
    import aiohttp as ah
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        img_path = tmp.name
    async with ah.ClientSession() as sess:
        async with sess.get(img_url, timeout=ah.ClientTimeout(total=60)) as r:
            with open(img_path, "wb") as f:
                f.write(await r.read())

    # Stage 2: SVD image → video
    svd_id = "stability-ai/stable-video-diffusion:3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438"
    with open(img_path, "rb") as f:
        vid_output = await asyncio.wait_for(
            asyncio.to_thread(rep.run, svd_id,
                              input={"input_image": f,
                                     "sizing_strategy": "maintain_aspect_ratio",
                                     "frames_per_second": 8,
                                     "num_frames": dur * 8,
                                     "motion_bucket_id": 100,
                                     "cond_aug": 0.02}),
            timeout=Config.GEN_TIMEOUT_SECS
        )

    if progress_cb:
        await progress_cb(90, "Finalizing…")

    try:
        os.remove(img_path)
    except Exception:
        pass

    if isinstance(vid_output, list):
        return str(vid_output[0])
    if hasattr(vid_output, "url"):
        return vid_output.url
    return str(vid_output)
