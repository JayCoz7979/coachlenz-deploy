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
    """Prefer master/playlist manifests, then HLS over DASH."""
    u = url.lower()
    score = 0
    if "master" in u or "playlist" in u:
        score += 10
    if "/api/v3" in u:
        score += 5
    if ".m3u8" in u:
        score += 2
    return score


async def capture_hudl_stream(page_url: str, timeout_s: int = 75) -> dict:
    from playwright.async_api import async_playwright

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

            hudl_cookies = os.environ.get("HUDL_COOKIES", "").strip()
            if hudl_cookies:
                pw_cookies = [
                    {"name": n, "value": v, "domain": d.lstrip("."), "path": "/"}
                    for d, n, v in _cookie_pairs_from_netscape(hudl_cookies)
                ]
                if pw_cookies:
                    try:
                        await context.add_cookies(pw_cookies)
                    except Exception as e:
                        logger.warning(f"[hudl] could not apply HUDL_COOKIES: {e}")

            page = await context.new_page()

            def note_url(url: str):
                nonlocal total_requests
                total_requests += 1
                if re.search(r'\.(m3u8|mpd)', url, re.IGNORECASE):
                    found.add(url)
                if any(k in url.lower() for k in ("manifest", "playback", "stream", "/video", "media", "api/v3")):
                    seen_media.add(url[:160])

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
                await page.goto(page_url, wait_until="load", timeout=timeout_s * 1000)
            except Exception as e:
                raise HudlCaptureError(f"could not open Hudl page: {e}")

            # Force playback by every available means.
            await page.wait_for_timeout(3000)
            for sel in PLAY_SELECTORS:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click(timeout=1500, force=True)
                        await page.wait_for_timeout(600)
                except Exception:
                    continue
            try:
                await page.evaluate(
                    "() => { const v = document.querySelector('video'); if (v) { v.muted = true; v.play && v.play(); } }"
                )
            except Exception:
                pass
            try:
                await page.keyboard.press("k")
                await page.keyboard.press("Space")
            except Exception:
                pass

            # Poll for a manifest for up to the remaining budget.
            for _ in range(20):
                if found:
                    break
                await page.wait_for_timeout(1500)

            if not found:
                logger.warning(
                    f"[hudl] no manifest. requests={total_requests} media-ish URLs seen: "
                    + " | ".join(sorted(seen_media)[:12])
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
                "headers": {"User-Agent": USER_AGENT, "Referer": page_url, "Origin": "https://fan.hudl.com"},
            }
        finally:
            await browser.close()
