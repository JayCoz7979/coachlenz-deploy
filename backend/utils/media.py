"""ffprobe helpers shared by the ingest and detection workers."""
from typing import Any


def _parse_timecode(v: Any) -> float:
    """Seconds from a numeric string OR an ffprobe "HH:MM:SS.mmm" DURATION tag."""
    s = str(v).strip()
    if not s:
        return 0.0
    try:
        if ":" in s:
            parts = [float(p) for p in s.split(":")]
            while len(parts) < 3:
                parts.insert(0, 0.0)
            h, m, sec = parts[-3], parts[-2], parts[-1]
            return h * 3600 + m * 60 + sec
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def duration_from_probe(info: dict) -> float:
    """Robust duration (seconds) from an ffprobe JSON dict.

    Tries format.duration, then the video stream's duration, then any stream's
    duration, then a stream's "DURATION" tag (HH:MM:SS.mmm). Some containers
    (webm/mkv, some MP4/HLS) leave format.duration empty and only carry the
    duration on the stream or in tags, which previously stored a 0 and later
    hard-crashed detection with "Could not determine video duration".
    """
    if not isinstance(info, dict):
        return 0.0
    d = _parse_timecode((info.get("format") or {}).get("duration") or 0)
    if d > 0:
        return d
    streams = info.get("streams") or []
    for want_video in (True, False):
        for s in streams:
            if not isinstance(s, dict):
                continue
            if want_video and s.get("codec_type") != "video":
                continue
            sd = _parse_timecode(s.get("duration") or 0)
            if sd > 0:
                return sd
            tags = s.get("tags") or {}
            for k, v in (tags.items() if isinstance(tags, dict) else []):
                if str(k).lower() == "duration" and v:
                    td = _parse_timecode(v)
                    if td > 0:
                        return td
    return 0.0
