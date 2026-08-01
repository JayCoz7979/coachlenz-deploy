"""
Single source of truth for "what happens when a coach pastes this link."

Both the import UI (the green "no Hudl account needed" badge) and the ingest worker
must agree on whether a pasted URL imports with NO login or will fall to the
browser-capture/login path. When the badge and the worker used separate heuristics
they drifted, and a coach could be promised "no account needed" on a link that then
failed on private film. `classify_ingest_url` is the one classifier the badge calls
(via POST /ingest/check-url) and the worker's behavior mirrors.

Pure + side-effect-free (no network): safe to call on every keystroke.
"""
from urllib.parse import urlparse

from backend.services.hudl_capture import unwrap_hudl_direct_url, _looks_like_direct_video

SUPPORTED_SOURCES = [
    "youtube.com", "youtu.be",
    "hudl.com",
    "vimeo.com",
    "drive.google.com",
    "dropbox.com",
    "facebook.com", "fb.watch",
    "twitter.com", "x.com",
    "instagram.com",
    "tiktok.com",
    "streamable.com",
    "dailymotion.com",
    "wistia.com",
    "loom.com",
]

SOURCE_LABELS = {
    "youtube": "YouTube",
    "hudl": "Hudl",
    "nfhs": "NFHS Network",
    "vimeo": "Vimeo",
    "google_drive": "Google Drive",
    "dropbox": "Dropbox",
    "facebook": "Facebook",
    "generic": "Video link",
}


def detect_source_type(url: str) -> str:
    url_lower = (url or "").lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    if "hudl.com" in url_lower:
        return "hudl"
    if "vimeo.com" in url_lower:
        return "vimeo"
    if "drive.google.com" in url_lower:
        return "google_drive"
    if "dropbox.com" in url_lower:
        return "dropbox"
    if "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "facebook"
    if "nfhsnetwork.com" in url_lower:
        return "nfhs"
    return "generic"


def is_hudl_no_login(url: str) -> bool:
    """True when a Hudl URL imports with NO login: it's the emailed Download/bulk
    wrapper that forwards to a pre-signed file, OR a directly-pasted Hudl direct
    file (vtemp/vg/vcloud.hudl.com or a video-extension URL). This is the EXACT
    condition the worker uses to take the plain-download path — keep them in lockstep."""
    if detect_source_type(url) != "hudl":
        return False
    return bool(unwrap_hudl_direct_url(url)) or _looks_like_direct_video(url)


def classify_ingest_url(url: str) -> dict:
    """Authoritative answer for the paste-a-link UI. Returns:
      source_type: internal source key (youtube/hudl/nfhs/vimeo/...)
      label:       human label for that source
      status:      'no_login'  -> imports with no account, high confidence (green)
                   'public_ok' -> public/shared imports with no login; PRIVATE needs a
                                  login (Download link / connected account) — amber-green
                   'invalid'   -> not a usable public http(s) link
      hudl_direct: True only for the Hudl no-login Download/direct-file path
      message:     one-line coach-facing guidance for the badge
    """
    u = (url or "").strip()
    if not u:
        return {"source_type": "generic", "label": "", "status": "invalid",
                "hudl_direct": False, "message": ""}

    # Light validity check only (no DNS/network — the real SSRF guard runs at import).
    try:
        p = urlparse(u)
    except Exception:
        p = None
    if not p or p.scheme.lower() not in ("http", "https") or not p.hostname:
        return {"source_type": "generic", "label": "", "status": "invalid",
                "hudl_direct": False,
                "message": "That doesn't look like a web link. Paste a full https:// URL, "
                           "or use the Upload File tab."}

    source_type = detect_source_type(u)
    label = SOURCE_LABELS.get(source_type, "Video link")
    hudl_direct = is_hudl_no_login(u)

    if source_type == "youtube":
        return {"source_type": source_type, "label": label, "status": "no_login",
                "hudl_direct": False,
                "message": "Public or unlisted YouTube link — imports in HD, no account needed."}

    if hudl_direct:
        return {"source_type": source_type, "label": label, "status": "no_login",
                "hudl_direct": True,
                "message": "Hudl download link detected — no Hudl account needed. It carries the "
                           "video file itself, so we import it directly. These expire fast — import now."}

    if source_type == "hudl":
        return {"source_type": source_type, "label": label, "status": "public_ok",
                "hudl_direct": False,
                "message": "Hudl link — we'll capture and import it automatically. Shared/public "
                           "reels need no login. For PRIVATE team film, use Hudl's Download button "
                           "and paste that link (no account needed), or connect your Hudl account once."}

    if source_type == "nfhs":
        return {"source_type": source_type, "label": label, "status": "public_ok",
                "hudl_direct": False,
                "message": "NFHS Network link — free events import directly. Subscription games need a "
                           "connected NFHS login, or download from NFHS and use Upload File."}

    # vimeo / google_drive / dropbox / facebook / generic direct links
    return {"source_type": source_type, "label": label, "status": "no_login",
            "hudl_direct": False,
            "message": "We'll import this link directly — no account needed. Make sure sharing is "
                       "set to “anyone with the link.”"}
