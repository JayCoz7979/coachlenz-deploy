"""
Hudl stream capture.

Hudl (both fan.hudl.com and the hudl.com coaching platform) serves film as
token-gated HLS via THEOplayer — there is NO content DRM, but the manifest URL is
generated client-side after the player authenticates the page session. yt-dlp
cannot reach it directly ("Unsupported URL").

This module drives a real headless Chromium browser to load the Hudl watch page,
lets the player request its HLS master manifest, and captures:
  - the .m3u8 manifest URL
  - the cookies the session established
  - the User-Agent / Referer needed to fetch segments

The caller then hands these to yt-dlp, which downloads the (clear) HLS stream.

Private/login-gated film: set HUDL_COOKIES (Netscape cookie file contents) in the
environment to authenticate the browser session for non-public film.
"""
import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Play-button selectors seen across Hudl's THEOplayer skins.
PLAY_SELECTORS = [
    ".theoplayer-skin .vds-play-button",
    "button[aria-label*='play' i]",
    ".vjs-big-play-button",
    "button.theo-play-button",
    "[data-testid='play-button']",
    ".theoplayer-container",
    "video",
]


class HudlCaptureError(Exception):
    pass


def _cookie_pairs_from_netscape(text: str) -> list[tuple[str, str, str]]:
    """Parse a Netscape cookies.txt into (domain, name, value) tuples."""
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


async def capture_hudl_stream(page_url: str, timeout_s: int = 60) -> dict:
    """
    Returns: {"manifest_url": str, "cookies": str (Netscape), "headers": dict}
    Raises HudlCaptureError if no stream could be captured.
    """
    from playwright.async_api import async_playwright

    manifest_candidates: list[str] = []
    loop = asyncio.get_event_loop()
    first_master = loop.create_future()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        try:
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 720},
            )

            # Optional auth for private film
            hudl_cookies = os.environ.get("HUDL_COOKIES", "").strip()
            if hudl_cookies:
                pw_cookies = []
                for domain, name, value in _cookie_pairs_from_netscape(hudl_cookies):
                    pw_cookies.append({
                        "name": name, "value": value,
                        "domain": domain.lstrip("."), "path": "/",
                    })
                if pw_cookies:
                    try:
                        await context.add_cookies(pw_cookies)
                    except Exception as e:
                        logger.warning(f"[hudl] could not apply HUDL_COOKIES: {e}")

            page = await context.new_page()

            def _record(url: str):
                if ".m3u8" in url and url not in manifest_candidates:
                    manifest_candidates.append(url)
                    # Prefer a master/playlist manifest as the definitive hit.
                    if not first_master.done() and (
                        "master" in url.lower() or "playlist" in url.lower() or "/api/v3" in url.lower()
                    ):
                        first_master.set_result(url)

            page.on("request", lambda req: _record(req.url))
            page.on("response", lambda resp: _record(resp.url))

            try:
                await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
            except Exception as e:
                raise HudlCaptureError(f"could not open Hudl page: {e}")

            # Nudge playback so the player fetches its manifest.
            await page.wait_for_timeout(2500)
            for sel in PLAY_SELECTORS:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click(timeout=1500, force=True)
                        await page.wait_for_timeout(800)
                except Exception:
                    continue

            # Wait for a master manifest, or fall back to any .m3u8 seen.
            manifest_url: Optional[str] = None
            try:
                manifest_url = await asyncio.wait_for(first_master, timeout=timeout_s)
            except asyncio.TimeoutError:
                if manifest_candidates:
                    manifest_url = manifest_candidates[0]

            if not manifest_url:
                # Give the network a last moment, then re-check.
                await page.wait_for_timeout(3000)
                if manifest_candidates:
                    manifest_url = manifest_candidates[0]

            if not manifest_url:
                raise HudlCaptureError(
                    "no video stream found — the film may be private/login-gated, "
                    "or Hudl changed its player"
                )

            # Capture session cookies as a Netscape cookies.txt for yt-dlp.
            cookies = await context.cookies()
            netscape_lines = ["# Netscape HTTP Cookie File"]
            for c in cookies:
                domain = c.get("domain", "")
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                secure = "TRUE" if c.get("secure") else "FALSE"
                expiry = str(int(c.get("expires", 0)) if c.get("expires", 0) and c["expires"] > 0 else 0)
                netscape_lines.append(
                    "\t".join([domain, flag, c.get("path", "/"), secure, expiry, c.get("name", ""), c.get("value", "")])
                )

            logger.info(f"[hudl] captured manifest ({len(manifest_candidates)} m3u8 seen): {manifest_url[:120]}")
            return {
                "manifest_url": manifest_url,
                "cookies": "\n".join(netscape_lines),
                "headers": {"User-Agent": USER_AGENT, "Referer": page_url, "Origin": "https://fan.hudl.com"},
            }
        finally:
            await browser.close()
