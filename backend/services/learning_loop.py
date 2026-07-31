"""
Per-account learning loop (Engine §14).

One account, one model, one truth. A coach edits a play the AI tagged; we record
the (old -> new) label correction, roll a per-account quality score, and — when
the SAME AI mislabel is corrected the same way enough times — propose an account
adjustment the coach can accept. An accepted adjustment relabels matching plays in
that account's future reports, and NOTHING crosses accounts.

The scoring / proposal / apply logic here is pure and deterministic (no DB, no
model call) so it is fully unit-testable; the async helpers at the bottom are the
thin DB write path used by the events router and the reports worker.
"""
import logging
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── what counts as a correctable "label" ─────────────────────────────────────
# First-class categorical scheme reads the AI makes and a coach fixes. Numeric
# facts (down, distance, yards, time) are corrections of fact, not labeling bias,
# so they are deliberately excluded from the learning loop.
CORRECTABLE_LABEL_FIELDS = frozenset({
    "side", "event_type", "formation", "play_type", "personnel",
    "defensive_front", "coverage", "blitz", "result", "player",
})
# Scheme labels that live in extra_data (football concepts, basketball reads).
EXTRA_DATA_LABEL_FIELDS = frozenset({
    "run_concept", "pass_concept", "run_direction", "run_gap", "coverage_shell",
    "shot_zone", "shot_type", "screen_type", "defensive_scheme", "play_action",
})
ALL_LABEL_FIELDS = CORRECTABLE_LABEL_FIELDS | EXTRA_DATA_LABEL_FIELDS

# ── thresholds (spec §14) ────────────────────────────────────────────────────
# "After 10+ corrections in the same category" -> eligible to propose.
MIN_CATEGORY_CORRECTIONS = 10
# "Same correction direction 8+ out of 10" -> STRONG systematic signal.
STRONG_SUPPORT = 8
# A dominant mapping must also be the clear majority of that field's corrections.
DOMINANT_FRACTION = 0.6
# "5+ contradictions on the same play type" -> surface, don't auto-adjust.
NOISE_CONTRADICTIONS = 5


def _norm(v: Any) -> str:
    """Normalize a label value for comparison: str, trimmed, lowercased, leading
    '#' stripped (jerseys). None/empty -> ''."""
    if v is None:
        return ""
    return str(v).strip().lstrip("#").lower()


def _empty(v: Any) -> bool:
    return _norm(v) in ("", "none", "null", "unknown", "n/a")


# ── signal classification (pure) ─────────────────────────────────────────────
def classify_signal(old: Any, new: Any) -> Optional[str]:
    """Classify one label change. Returns:
      'high'    — added specificity (AI had nothing, coach set a value)
      'low'     — removed detail (coach blanked a value the AI had; likely misclick)
      'reclass' — relabeled A -> B (the systematic-vs-noise call happens in aggregate)
      None      — not a real correction (no change, or empty->empty)
    """
    if _norm(old) == _norm(new):
        return None
    o_empty, n_empty = _empty(old), _empty(new)
    if o_empty and n_empty:
        return None
    if o_empty and not n_empty:
        return "high"
    if not o_empty and n_empty:
        return "low"
    return "reclass"


def diff_label_changes(
    before: Dict[str, Any],
    after: Dict[str, Any],
) -> List[Tuple[str, Any, Any, str]]:
    """Given a play's label values before and after a coach edit, return the list
    of (field, old, new, signal) for every LABEL field that actually changed."""
    out: List[Tuple[str, Any, Any, str]] = []
    for field in ALL_LABEL_FIELDS:
        if field not in after:
            continue
        old, new = before.get(field), after.get(field)
        sig = classify_signal(old, new)
        if sig:
            out.append((field, old, new, sig))
    return out


# ── adjustment proposal (pure) ───────────────────────────────────────────────
def propose_adjustment(corrections: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Given the AI-origin 'reclass' corrections for ONE (sport, field), decide
    whether a systematic mapping has emerged.

    Each correction dict needs 'old_value' and 'new_value'. Returns a proposal
    {from_value, to_value, support_count, dominant, contradiction} or None when
    there aren't enough corrections yet.

    Rules: need >= MIN_CATEGORY_CORRECTIONS total; a single from->to mapping that
    reaches STRONG_SUPPORT occurrences AND >= DOMINANT_FRACTION of the field's
    corrections is proposed. Otherwise, if the same 'from' fans out to many 'to's
    with no winner, it's flagged as contradiction (noise) and nothing is proposed.
    """
    reclass = [(c.get("old_value"), c.get("new_value")) for c in corrections
               if classify_signal(c.get("old_value"), c.get("new_value")) == "reclass"]
    total = len(reclass)
    if total < MIN_CATEGORY_CORRECTIONS:
        return None

    pair_counts = Counter((_norm(o), _norm(n)) for o, n in reclass)
    # Keep a representative original-cased value for the winning pair.
    repr_value: Dict[Tuple[str, str], Tuple[Any, Any]] = {}
    for o, n in reclass:
        repr_value.setdefault((_norm(o), _norm(n)), (o, n))

    (top_pair, support), = pair_counts.most_common(1)
    dominant = support >= STRONG_SUPPORT and support >= DOMINANT_FRACTION * total

    # Contradiction: one 'from' that the coach sends to many different 'to's.
    from_fanout: Dict[str, set] = defaultdict(set)
    for (o, n) in pair_counts:
        from_fanout[o].add(n)
    contradiction = any(len(tos) >= 2 and pair_counts.most_common(1)[0][1] < STRONG_SUPPORT
                        for tos in from_fanout.values())

    if not dominant:
        return {"from_value": None, "to_value": None, "support_count": support,
                "dominant": False, "contradiction": contradiction}

    from_v, to_v = repr_value[top_pair]
    return {"from_value": from_v, "to_value": to_v, "support_count": support,
            "dominant": True, "contradiction": False}


# ── apply (pure) ─────────────────────────────────────────────────────────────
def _event_field_value(event: Any, field: str) -> Any:
    if field in EXTRA_DATA_LABEL_FIELDS:
        ex = getattr(event, "extra_data", None) or {}
        return ex.get(field)
    return getattr(event, field, None)


def _set_event_field(event: Any, field: str, value: Any) -> None:
    if field in EXTRA_DATA_LABEL_FIELDS:
        ex = dict(getattr(event, "extra_data", None) or {})
        ex[field] = value
        event.extra_data = ex
    else:
        setattr(event, field, value)


def apply_adjustments(events: List[Any], adjustments: List[Dict[str, Any]]) -> int:
    """Relabel in-memory events per a list of ACTIVE adjustments (dicts with
    field/from_value/to_value). Mutates the event objects in place and returns the
    number of field values changed. Caller must NOT commit these events — the loop
    normalizes the report's view, it does not overwrite the stored film.
    """
    if not events or not adjustments:
        return 0
    # Index by field -> {normalized from: to}
    by_field: Dict[str, Dict[str, Any]] = defaultdict(dict)
    for a in adjustments:
        f = a.get("field")
        if f in ALL_LABEL_FIELDS:
            by_field[f][_norm(a.get("from_value"))] = a.get("to_value")

    changed = 0
    for ev in events:
        for field, mapping in by_field.items():
            cur = _event_field_value(ev, field)
            hit = mapping.get(_norm(cur))
            if hit is not None and _norm(cur) != _norm(hit):
                _set_event_field(ev, field, hit)
                changed += 1
    return changed


# ── DB write path (async, thin) ──────────────────────────────────────────────
async def record_corrections(
    db,
    *,
    organization_id,
    user_id,
    event,
    sport: str,
    changes: List[Tuple[str, Any, Any, str]],
    manual_mode: bool,
) -> int:
    """Persist correction rows for a coach's edit, roll the account quality score,
    and (unless Manual Mode) recompute the affected adjustments. Best-effort:
    logs and swallows its own errors so it can never break the underlying edit.
    Returns the number of corrections recorded."""
    if not changes:
        return 0
    from sqlalchemy import select
    from backend.models.learning import CoachLabelCorrection, LabelQualityScore

    ex = getattr(event, "extra_data", None) or {}
    was_auto = bool(ex.get("auto_detected"))
    ai_conf = ex.get("confidence")
    category = getattr(event, "play_type", None) or (getattr(event, "event_type", None))

    try:
        for field, old, new, signal in changes:
            db.add(CoachLabelCorrection(
                organization_id=organization_id, user_id=user_id,
                event_id=getattr(event, "id", None), game_id=getattr(event, "game_id", None),
                sport=sport, field=field, category=category,
                old_value=(None if old is None else str(old)),
                new_value=(None if new is None else str(new)),
                was_auto_detected=was_auto, ai_confidence=ai_conf, signal=signal,
            ))

        # Roll the per-account quality score (one row per org).
        score = (await db.execute(
            select(LabelQualityScore).where(LabelQualityScore.organization_id == organization_id)
        )).scalar_one_or_none()
        if score is None:
            score = LabelQualityScore(organization_id=organization_id)
            db.add(score)
        for _f, _o, _n, signal in changes:
            score.total_corrections = (score.total_corrections or 0) + 1
            if signal == "high":
                score.high_count = (score.high_count or 0) + 1
            elif signal == "low":
                score.low_count = (score.low_count or 0) + 1
            elif signal == "reclass":
                score.reclass_count = (score.reclass_count or 0) + 1

        await db.commit()
    except Exception as e:
        logger.error(f"[learning] failed to record corrections: {e}")
        try:
            await db.rollback()
        except Exception:
            pass
        return 0

    # Recompute adjustments for the AI-origin fields that changed (opt-out via Manual Mode).
    if was_auto and not manual_mode:
        fields = {f for f, _o, _n, sig in changes if sig == "reclass"}
        for field in fields:
            try:
                await recompute_adjustment(db, organization_id, sport, field)
            except Exception as e:
                logger.error(f"[learning] recompute failed ({field}): {e}")
    return len(changes)


async def recompute_adjustment(db, organization_id, sport: str, field: str) -> None:
    """Re-derive the systematic mapping for one (org, sport, field) from its
    AI-origin corrections and upsert a pending adjustment when one emerges. Marks
    the score's systematic_count when a NEW proposal is created."""
    from sqlalchemy import select
    from backend.models.learning import (
        CoachLabelCorrection, AccountLearningAdjustment, LabelQualityScore,
    )

    rows = (await db.execute(
        select(CoachLabelCorrection).where(
            CoachLabelCorrection.organization_id == organization_id,
            CoachLabelCorrection.sport == sport,
            CoachLabelCorrection.field == field,
            CoachLabelCorrection.was_auto_detected.is_(True),
        )
    )).scalars().all()

    proposal = propose_adjustment([{"old_value": r.old_value, "new_value": r.new_value} for r in rows])
    if not proposal or not proposal.get("dominant"):
        return

    existing = (await db.execute(
        select(AccountLearningAdjustment).where(
            AccountLearningAdjustment.organization_id == organization_id,
            AccountLearningAdjustment.sport == sport,
            AccountLearningAdjustment.field == field,
            AccountLearningAdjustment.from_value == proposal["from_value"],
            AccountLearningAdjustment.to_value == proposal["to_value"],
        )
    )).scalar_one_or_none()

    if existing is None:
        db.add(AccountLearningAdjustment(
            organization_id=organization_id, sport=sport, field=field,
            from_value=proposal["from_value"], to_value=proposal["to_value"],
            support_count=proposal["support_count"], status="pending",
            note=f"{proposal['support_count']} corrections changed '{proposal['from_value']}' to '{proposal['to_value']}'",
        ))
        score = (await db.execute(
            select(LabelQualityScore).where(LabelQualityScore.organization_id == organization_id)
        )).scalar_one_or_none()
        if score is not None:
            score.systematic_count = (score.systematic_count or 0) + 1
    elif existing.status != "rejected":
        # Keep support fresh; a rejected proposal stays rejected until reset.
        existing.support_count = proposal["support_count"]
    await db.commit()


async def active_adjustments_for(db, organization_id, sport: str) -> List[Dict[str, Any]]:
    """Active adjustments to apply to a report for this org+sport. Empty list is
    the safe default (no learning applied)."""
    from sqlalchemy import select
    from backend.models.learning import AccountLearningAdjustment

    rows = (await db.execute(
        select(AccountLearningAdjustment).where(
            AccountLearningAdjustment.organization_id == organization_id,
            AccountLearningAdjustment.sport == sport,
            AccountLearningAdjustment.status == "active",
        )
    )).scalars().all()
    return [{"field": r.field, "from_value": r.from_value, "to_value": r.to_value} for r in rows]
