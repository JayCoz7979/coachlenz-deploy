"""
Report-scoped AI Coach Chat engine (Engine §13).

A coach asks a plain-English question about a finished scouting report; the Film
Assistant answers ONLY from that report's film data — the generated Coach Layer
sections, the tendency / heat-zone data, and the tagged plays (video cutups). It
never fabricates a tendency (a hallucinated tendency costs games), keeps answers
short, and cites the exact cutups a coach can jump to.

Design guarantees enforced here (not left to the model's goodwill):
  * If the answer is not grounded in the film, the response is the canonical
    "upload another game" line — deterministically, server-side.
  * Cited cutups are looked up by integer id against the real play list, so the
    model cannot invent a clip that isn't in the film.
  * total_cost_usd is measured from token usage to 6 decimals (UATP / standing #6).

No framework, DB, or cross-account data lives in here — the router hands this
module exactly one report's data and gets back a structured answer.
"""
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import anthropic

from backend.config import settings

logger = logging.getLogger(__name__)

# ASYNC client (matches report_writer): the sync client would block the API event
# loop for the whole 2-8s of an LLM call, stalling every other request.
client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

# Single source of truth for the model — config, not a hardcode (standing #12).
MODEL = settings.ANTHROPIC_MODEL

# Per-1M-token rates for the report model, kept in sync with worker_ai_detect's
# MODEL_PRICING for claude-sonnet-4-6. Used only to turn measured tokens into $.
_PRICING = {"in": 3.0, "out": 15.0, "cache_w": 3.75, "cache_r": 0.30}

# UATP identity (matches services.agent_log). The assistant discloses who it is.
AGENT_NAME = "Film Assistant"
AGENT_ROLE = "your AI film assistant"

# Below this the answer is still returned but flagged for human review (UATP
# escalation): the agent does not present a shaky read as fact.
ESCALATION_THRESHOLD = 0.65

# The one line the coach sees when the film doesn't cover the question. Returned
# verbatim and deterministically whenever the model can't ground an answer.
NOT_IN_FILM = ("I didn't see enough of that situation in this film. "
               "Upload another game to build the sample.")

# Keep the model's context bounded. The tendency/heat JSON is cached (cheap on
# repeat turns) but a runaway summary shouldn't blow the window on turn one.
_MAX_SUMMARY_CHARS = 60_000
_MAX_CUTUPS = 80
# How many prior turns (user+assistant messages) to replay for continuity.
_HISTORY_LIMIT = 12

_SYSTEM_RULES = f"""You are the CoachLenz {AGENT_NAME}, {AGENT_ROLE}.

A high school or small-college coach is asking about ONE finished scouting report.
Everything you know about this opponent is in the REPORT CONTEXT the user turn
provides: the written scouting sections, the tendency and shot/run heat data, and
a numbered list of tagged plays (video cutups).

Hard rules:
- Answer ONLY from the film data in the context. If the context does not contain
  enough to answer, you have NOT seen it — do not guess, infer, or generalize.
- Never invent a tendency, number, player, or play. A made-up tendency costs games.
- Keep answers tight: 2-4 sentences. Coaches are busy.
- When your answer points to specific plays, cite them by their [id] from the
  cutup list so the coach can jump straight to the film.
- Be concrete and directive — talk like a coach in a film session, not a chatbot.

Respond with ONLY a JSON object, no prose around it:
{{"answered": true|false,
  "answer": "your 2-4 sentence answer",
  "confidence": 0.0-1.0,
  "cutup_ids": [list of integer ids from the cutup list you referenced]}}

Set "answered" to false when the film doesn't cover the question. When false, leave
"answer" empty, "cutup_ids" empty, and give your best confidence that it's absent.
"confidence" is how sure you are of the answer given the film sample (sample size,
clarity), 0.0 = no idea, 1.0 = certain."""


# ── cutups ───────────────────────────────────────────────────────────────────
def _get(e: Any, field: str):
    return e.get(field) if isinstance(e, dict) else getattr(e, field, None)


def _cutup_label(e: Any) -> str:
    """One-line, scan-fast label for a tagged play, from whatever fields exist."""
    t = _get(e, "time_seconds")
    bits: List[str] = []
    if t is not None:
        bits.append(f"t={int(t)}s")
    et = _get(e, "event_type")
    if et:
        bits.append(str(et))
    down, dist = _get(e, "down"), _get(e, "distance")
    if down:
        bits.append(f"{down}&{dist}" if dist is not None else f"down {down}")
    for f in ("formation", "play_type", "coverage"):
        v = _get(e, f)
        if v:
            bits.append(str(v))
    player = _get(e, "player")
    if player:
        bits.append(f"#{player}")
    res = _get(e, "result")
    if res:
        bits.append(f"result: {res}")
    return " | ".join(bits) or "play"


def build_cutups(events) -> List[Dict[str, Any]]:
    """Turn this report's tagged plays into a stable, id'd cutup list. Skips scout
    bookkeeping rows and plays with no playable anchor (no time). Capped so the
    context stays bounded on a huge game."""
    cutups: List[Dict[str, Any]] = []
    for e in events:
        if _get(e, "event_type") == "scout_meta":
            continue
        if _get(e, "time_seconds") is None:
            continue
        cutups.append({
            "id": len(cutups) + 1,
            "clip_id": str(_get(e, "clip_id")) if _get(e, "clip_id") else None,
            "time_seconds": float(_get(e, "time_seconds")),
            "event_type": _get(e, "event_type"),
            "player": _get(e, "player"),
            "label": _cutup_label(e),
        })
        if len(cutups) >= _MAX_CUTUPS:
            break
    return cutups


# ── context ──────────────────────────────────────────────────────────────────
def build_report_context(report: Any, summary: Optional[dict],
                         cutups: List[Dict[str, Any]]) -> str:
    """Assemble the full film context for one report: written Coach Layer sections
    + tendency/heat data + the numbered cutup list. Pure string assembly; the
    caller is responsible for passing only this org's report."""
    parts: List[str] = []
    parts.append(f"REPORT: {_get(report, 'title')}  "
                 f"(sport: {_get(report, 'sport')}, type: {_get(report, 'report_type')})")

    sections = _get(report, "prose_sections") or []
    if sections:
        parts.append("\n=== COACH LAYER (written scouting report) ===")
        for s in sections:
            heading = (s or {}).get("heading") or "Section"
            body = (s or {}).get("body") or ""
            parts.append(f"\n## {heading}\n{body}")

    if summary:
        try:
            blob = json.dumps(summary, default=str)
        except Exception:
            blob = ""
        if blob:
            if len(blob) > _MAX_SUMMARY_CHARS:
                blob = blob[:_MAX_SUMMARY_CHARS] + " …(truncated)"
            parts.append("\n=== TENDENCY & HEAT DATA (numbers behind the report) ===")
            parts.append(blob)

    parts.append("\n=== VIDEO CUTUPS (tagged plays — cite by [id]) ===")
    if cutups:
        for c in cutups:
            parts.append(f"[{c['id']}] {c['label']}")
    else:
        parts.append("(no tagged plays available for this report)")

    return "\n".join(parts)


# ── cost ─────────────────────────────────────────────────────────────────────
def cost_usd(usage) -> float:
    """Measured token usage -> dollars, to 6 decimals (UATP standing rule #6)."""
    if usage is None:
        return 0.0
    c = (
        (getattr(usage, "input_tokens", 0) or 0) * _PRICING["in"]
        + (getattr(usage, "output_tokens", 0) or 0) * _PRICING["out"]
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * _PRICING["cache_w"]
        + (getattr(usage, "cache_read_input_tokens", 0) or 0) * _PRICING["cache_r"]
    ) / 1_000_000
    return round(c, 6)


# ── parsing ──────────────────────────────────────────────────────────────────
def _first_text(message) -> str:
    try:
        for block in (message.content or []):
            if getattr(block, "type", None) == "text" or hasattr(block, "text"):
                return (block.text or "").strip()
    except Exception:
        pass
    return ""


def _parse_answer(raw: str) -> Dict[str, Any]:
    """Tolerant parse of the model's JSON object. Anything we can't read as a
    grounded answer collapses to 'not in film' — we never fabricate on a parse
    failure."""
    text = (raw or "").strip()
    if "```" in text:
        # strip a ```json fence
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    # Grab the outermost {...} if there's stray prose.
    if "{" in text and "}" in text:
        text = text[text.index("{"): text.rindex("}") + 1]
    try:
        obj = json.loads(text)
    except Exception:
        return {"answered": False, "answer": "", "confidence": None, "cutup_ids": []}
    if not isinstance(obj, dict):
        return {"answered": False, "answer": "", "confidence": None, "cutup_ids": []}

    answered = bool(obj.get("answered"))
    answer = str(obj.get("answer") or "").strip()
    conf = obj.get("confidence")
    try:
        conf = max(0.0, min(1.0, float(conf))) if conf is not None else None
    except (TypeError, ValueError):
        conf = None
    ids = obj.get("cutup_ids") or []
    if not isinstance(ids, list):
        ids = []
    clean_ids: List[int] = []
    for x in ids:
        try:
            clean_ids.append(int(x))
        except (TypeError, ValueError):
            continue
    # An "answered" with no actual text is not an answer.
    if answered and not answer:
        answered = False
    return {"answered": answered, "answer": answer, "confidence": conf, "cutup_ids": clean_ids}


def _resolve_cutups(ids: List[int], cutups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map model-cited [id]s back to real cutups. Invalid ids are dropped — this is
    the guard against a hallucinated clip reference."""
    by_id = {c["id"]: c for c in cutups}
    out, seen = [], set()
    for i in ids:
        if i in by_id and i not in seen:
            seen.add(i)
            out.append(by_id[i])
    return out


def band(score: Optional[float]) -> str:
    if score is None:
        return "unknown"
    if score >= 0.8:
        return "high"
    if score >= ESCALATION_THRESHOLD:
        return "medium"
    return "low"


# ── the call ─────────────────────────────────────────────────────────────────
async def answer_question(
    *,
    report_context: str,
    cutups: List[Dict[str, Any]],
    history: List[Dict[str, str]],
    question: str,
) -> Dict[str, Any]:
    """Ask the model a report-scoped question and return a fully-resolved answer.

    Returns a dict:
      content (str), answered (bool), confidence (float|None),
      cutups (list[dict]), cost_usd (float), needs_review (bool)

    The report_context is sent as a cache_control:ephemeral system block so repeat
    turns on the same report reuse it cheaply (CLAUDE prompt-caching requirement).
    """
    system = [
        {"type": "text", "text": _SYSTEM_RULES},
        {"type": "text",
         "text": "REPORT CONTEXT (the only film you may use):\n\n" + report_context,
         "cache_control": {"type": "ephemeral"}},
    ]
    messages = list(history) + [{"role": "user", "content": question}]

    message = await client.messages.create(
        model=MODEL,
        max_tokens=700,          # 2-4 sentences + a short id list; no essays
        system=system,
        messages=messages,
    )
    parsed = _parse_answer(_first_text(message))
    cost = cost_usd(getattr(message, "usage", None))

    if not parsed["answered"]:
        # Deterministic no-fabrication guarantee: the coach gets the canonical line,
        # never an invented answer or invented cutups.
        return {
            "content": NOT_IN_FILM,
            "answered": False,
            "confidence": parsed["confidence"],
            "cutups": [],
            "cost_usd": cost,
            "needs_review": False,
        }

    resolved = _resolve_cutups(parsed["cutup_ids"], cutups)
    conf = parsed["confidence"]
    return {
        "content": parsed["answer"],
        "answered": True,
        "confidence": conf,
        "cutups": resolved,
        "cost_usd": cost,
        # UATP escalation: a low-confidence answer is surfaced but flagged so the
        # coach knows to verify it rather than take it as fact.
        "needs_review": (conf is not None and conf < ESCALATION_THRESHOLD),
    }


def to_messages(rows) -> List[Dict[str, str]]:
    """Map stored chat rows (oldest->newest) into Anthropic message dicts, keeping
    only the last _HISTORY_LIMIT for a bounded window."""
    msgs: List[Dict[str, str]] = []
    for r in rows:
        role = _get(r, "role")
        content = _get(r, "content")
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content})
    return msgs[-_HISTORY_LIMIT:]
