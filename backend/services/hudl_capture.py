"""
Hudl stream capture.

Hudl (both fan.hudl.com and the hudl.com coaching platform) serves film as
token-gated streaming (HLS .m3u8 or DASH .mpd) via THEOplayer — there is NO
content DRM, but the manifest URL is generated client-side after the player
authenticates the page session. yt-dlp cannot reach it directly.

This module drives a real headless Chromium browser to load the Hudl watch page,
forces playback, and captures the manifest URL — from direct media requests AND
from JSON API/GraphQL response bodies — plus the session cookies/headers needed
to fetch it. The caller hands these to yt-dlp/ffmpeg to download the clear stream.

Private/login-gated film: set HUDL_COOKIES (Netscape cookie file contents) in the
environment to authenticate the browser session for non-public film.
"""
import asyncio
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Matches manifest URLs anywhere (in request URLs or inside JSON bodies).
MANIFEST_RE = re.compile(r'https?://[^\s"\'\\]+?\.(?:m3u8|mpd)[^\s"\'\\]*', re.IGNORECASE)

PLAY_SELECTORS = [
    ".theoplayer-skin .vds-play-button",
    "button[aria-label*='play' i]",
    ".vjs-big-play-button",
    "button.theo-play-button",
    "[data-testid='play-button']",
    ".theoplayer-container",
    ".video-js",
    "video",
]

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
"""


class HudlCaptureError(Exception):
    pass


def _cookie_pairs_from_netscape(text: str):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            domain, _flag, _path, _secure, _expiry, name, value = parts[:7]
            out.append((domain, name, value))
    return out


def _rank(url: str) -> int:
    """Prefer HLS/DASH master manifests, then highest-res direct MP4."""
    u = url.lower()
    score = 0
    if "master" in u or "playlist" in u:
        score += 20
    if ".m3u8" in u or ".mpd" in u:
        score += 15
    if ".mp4" in u:
        score += 10
    # Prefer higher resolution for direct files.
    for res, pts in (("1080", 4), ("720", 3), ("540", 2), ("480", 1)):
        if res in u:
            score += pts
            break
    return score


async def capture_hudl_stream(page_url: str, timeout_s: int = 75, cookies_env: str = "HUDL_COOKIES") -> dict:
    """
    Generic streaming-page capture (works for Hudl, NFHS Network, and similar
    THEOplayer/HLS sites). `cookies_env` names the env var holding a Netscape
    cookie file used to authenticate login-gated content.
    """
    from playwright.async_api import async_playwright
    from urllib.parse import urlparse

    parsed = urlparse(page_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    # Base domain for diagnostics (e.g. "hudl.com", "nfhsnetwork.com").
    site_domain = ".".join(parsed.netloc.lower().split(".")[-2:])

    found: set[str] = set()
    seen_media: set[str] = set()   # diagnostics
    total_requests = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--autoplay-policy=no-user-gesture-required",
            ]
        )
        try:
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1366, "height": 768},
                locale="en-US",
            )
            await context.add_init_script(STEALTH_JS)

            login_cookies = os.environ.get(cookies_env, "").strip()
            if login_cookies:
                pw_cookies = [
                    {"name": n, "value": v, "domain": d.lstrip("."), "path": "/"}
                    for d, n, v in _cookie_pairs_from_netscape(login_cookies)
                ]
                if pw_cookies:
                    try:
                        await context.add_cookies(pw_cookies)
                    except Exception as e:
                        logger.warning(f"[capture] could not apply {cookies_env}: {e}")

            page = await context.new_page()

            hudl_api_seen: set[str] = set()

            def note_url(url: str):
                nonlocal total_requests
                total_requests += 1
                low = url.lower()
                # Hudl serves highlights as direct MP4 on vg.hudl.com, and full
                # film sometimes as HLS/DASH. Only accept actual video URLs —
                # NOT thumbnails (.jpg) or other assets on the same host.
                if re.search(r'\.(m3u8|mpd|mp4)(\?|$)', low) or "/manifest" in low or "/playlist" in low:
                    found.add(url)
                if site_domain in low and any(k in low for k in ("api", "video", "playback", "stream", "vcloud", "graphql", "manifest", "vg.")):
                    hudl_api_seen.add(url[:180])

            page.on("request", lambda req: note_url(req.url))

            async def on_response(resp):
                try:
                    note_url(resp.url)
                    ct = (resp.headers or {}).get("content-type", "")
                    u = resp.url.lower()
                    # Scan likely API/JSON bodies for embedded manifest URLs.
                    if ("json" in ct or "javascript" in ct or "graphql" in u
                            or "playback" in u or "/api/" in u):
                        body = await resp.text()
                        for m in MANIFEST_RE.findall(body):
                            found.add(m.replace("\\u0026", "&").replace("\\/", "/"))
                except Exception:
                    pass

            page.on("response", lambda resp: asyncio.create_task(on_response(resp)))

            try:
                await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
            except Exception as e:
                raise HudlCaptureError(f"could not open Hudl page: {e}")

            await page.wait_for_timeout(3000)

            # Dismiss cookie/consent banners that block the player.
            consent_texts = ["Accept All", "Accept all", "Accept", "I Agree", "Agree", "Got it", "Continue", "OK", "Allow all"]
            for t in consent_texts:
                try:
                    btn = page.get_by_role("button", name=re.compile(t, re.IGNORECASE))
                    if await btn.count() > 0:
                        await btn.first.click(timeout=1200)
                        await page.wait_for_timeout(500)
                except Exception:
                    pass

            # Force playback by every available means.
            for sel in PLAY_SELECTORS:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click(timeout=1500, force=True)
                        await page.wait_for_timeout(600)
                except Exception:
                    continue
            # Click the center of the viewport (often the video surface).
            try:
                await page.mouse.click(683, 384)
            except Exception:
                pass
            try:
                await page.evaluate(
                    "() => { document.querySelectorAll('video').forEach(v => { try { v.muted = true; const p = v.play(); if (p && p.catch) p.catch(()=>{}); } catch(e){} }); }"
                )
            except Exception:
                pass
            try:
                await page.keyboard.press("k")
                await page.keyboard.press("Space")
            except Exception:
                pass

            # Poll: the most reliable source is the <video> element's own src,
            # which Hudl sets to a direct vg.hudl.com MP4 (or HLS/DASH) once the
            # player initializes. Read it directly each round.
            async def harvest_video_srcs():
                try:
                    urls = await page.evaluate(
                        """() => {
                            const out = [];
                            document.querySelectorAll('video').forEach(v => {
                                if (v.currentSrc) out.push(v.currentSrc);
                                if (v.src) out.push(v.src);
                                v.querySelectorAll('source').forEach(s => { if (s.src) out.push(s.src); });
                            });
                            return out;
                        }"""
                    )
                    for u in urls or []:
                        lu = u.lower()
                        if lu.startswith("http") and re.search(r'\.(mp4|m3u8|mpd)(\?|$)', lu):
                            found.add(u)
                except Exception:
                    pass

            for _ in range(24):
                await harvest_video_srcs()
                if found:
                    break
                await page.wait_for_timeout(1500)

            if not found:
                # Diagnose: report Hudl's own API calls + video element state.
                try:
                    vstate = await page.evaluate(
                        "() => { const v = document.querySelector('video'); return v ? {src: v.currentSrc||v.src||'', rs: v.readyState, err: v.error ? v.error.code : null, n: document.querySelectorAll('video').length} : {none:true}; }"
                    )
                except Exception:
                    vstate = "n/a"
                logger.warning(
                    f"[hudl] no manifest. requests={total_requests} videoState={vstate} "
                    f"hudl-api URLs: " + (" | ".join(sorted(hudl_api_seen)[:15]) or "NONE")
                )
                raise HudlCaptureError(
                    "no video stream found — the film may be private/login-gated, "
                    "or Hudl changed its player"
                )

            manifest_url = sorted(found, key=_rank, reverse=True)[0]

            cookies = await context.cookies()
            lines = ["# Netscape HTTP Cookie File"]
            for c in cookies:
                domain = c.get("domain", "")
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                secure = "TRUE" if c.get("secure") else "FALSE"
                exp = c.get("expires", 0) or 0
                expiry = str(int(exp) if exp and exp > 0 else 0)
                lines.append("\t".join([domain, flag, c.get("path", "/"), secure, expiry, c.get("name", ""), c.get("value", "")]))

            logger.info(f"[hudl] captured manifest ({len(found)} found, {total_requests} reqs): {manifest_url[:140]}")
            return {
                "manifest_url": manifest_url,
                "cookies": "\n".join(lines),
                "headers": {"User-Agent": USER_AGENT, "Referer": page_url, "Origin": origin},
            }
        finally:
            await browser.close()
