"""
Player-readability transform (Engine §11).

The Player Layer is written for a 16-year-old with no film-room experience:
6th-grade reading level, no percentages, no jargon, short sentences. This module
is the deterministic enforcement layer — whatever templated text the one-pager
builder produces is run through here so it CANNOT ship a percentage, a piece of
jargon, or a 20-word sentence. Pure and unit-testable; no framework, no model.
"""
import re
from typing import Optional

# Percentages become plain-English frequency words. A player never reads "63%".
def pct_to_words(pct: float) -> str:
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return ""
    if p >= 75:
        return "almost always"
    if p >= 60:
        return "usually"
    if p >= 40:
        return "sometimes"
    if p >= 25:
        return "not often"
    return "rarely"


# Coach/analyst jargon -> plain words. Lowercased whole-word (or phrase) swaps.
# Kept small and safe; add terms as real reports surface them.
_JARGON = [
    ("pick-and-roll", "pick and roll"),
    ("pick and roll", "pick and roll"),
    ("pnr", "pick and roll"),
    ("iso", "one-on-one"),
    ("isolation", "one-on-one"),
    ("ice coverage", "take away the middle"),
    ("ice", "take away the middle"),
    ("blob", "under-basket inbound"),
    ("slob", "sideline inbound"),
    ("efg", "shooting"),
    ("cover 3", "deep zone"),
    ("cover 2", "deep zone"),
    ("cover 1", "man coverage"),
    ("man coverage", "man coverage"),
    ("play-action", "play fake"),
    ("play action", "play fake"),
    ("rpo", "run-pass option"),
    ("perimeter", "outside"),
    ("transition", "the fast break"),
]

# "78% of the time" / "78 %" / "(63%)" -> a frequency word. The leading space is
# NOT consumed (that would glue the replacement to the previous word and break the
# next jargon swap's word boundary).
_PCT_RE = re.compile(r"\(?(\d{1,3}(?:\.\d+)?)\s*%\s*(?:of the time|of possessions|of snaps)?\)?")


def _swap_pct(m: re.Match) -> str:
    return pct_to_words(m.group(1))


def strip_percentages(text: str) -> str:
    """Replace every '63%' (and common trailing phrases) with a frequency word."""
    return _PCT_RE.sub(_swap_pct, text or "")


def _swap_jargon(text: str) -> str:
    out = text
    for term, plain in _JARGON:
        out = re.sub(rf"\b{re.escape(term)}\b", plain, out, flags=re.IGNORECASE)
    return out


def _clamp_words(text: str, max_words: int) -> str:
    """Cap word count so nothing runs long. A short multi-sentence phrase is kept
    WHOLE (e.g. "Drives hard. Wall off the paint." keeps its defensive instruction);
    only genuinely long text is trimmed to its first sentence, then hard-capped."""
    t = (text or "").strip()
    if not t:
        return ""
    if len(t.split()) <= max_words:
        return t                      # whole thing fits — keep every sentence
    first = re.split(r"(?<=[.!?])\s+", t, maxsplit=1)[0]
    fwords = first.split()
    if len(fwords) <= max_words:
        return first.strip()
    return " ".join(fwords[:max_words]).rstrip(",;:.") + "."


def plainify(text: str, max_words: int = 12) -> str:
    """Full pipeline: strip percentages -> swap jargon -> tidy spacing -> clamp
    to one short sentence. Idempotent enough to run on already-clean text."""
    if not text:
        return ""
    out = strip_percentages(text)
    out = _swap_jargon(out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    # Drop a leading '#<n>' duplication artifact and stray double punctuation.
    out = re.sub(r"\s+([.,;:])", r"\1", out)
    return _clamp_words(out, max_words)


def has_readability_violation(text: str) -> Optional[str]:
    """Return a reason string if text still breaks a hard §11 rule, else None.
    Used by tests (and callers that want to assert) — a percentage or an
    over-long sentence must never survive to a player-facing page."""
    if not text:
        return None
    if "%" in text:
        return "contains a percentage"
    if len(text.split()) > 12:
        return "sentence longer than 12 words"
    return None
