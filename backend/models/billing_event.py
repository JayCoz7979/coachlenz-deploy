from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class ProcessedStripeEvent(Base):
    """One row per Stripe webhook event we've already handled. The PK is Stripe's own
    event id, so a redelivery (Stripe delivers at-least-once and WILL resend) collides
    on insert and is skipped — turning at-least-once delivery into exactly-once effects.
    Without this, a redelivered invoice.payment_succeeded would grant referral credit
    twice."""
    __tablename__ = "processed_stripe_events"

    event_id = Column(String, primary_key=True)          # Stripe "evt_..." id
    event_type = Column(String)                          # for auditing/debugging
    processed_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class LiveTrackerExtraPayment(Base):
    """A PAID $7 Live Tracker Checkout Session for an org that already had the unlock
    from a different session (migration 068). Recorded for a human to refund in the
    Stripe dashboard; nothing is refunded automatically."""
    __tablename__ = "live_tracker_extra_payments"

    checkout_session_id = Column(String, primary_key=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    payment_intent_id = Column(String)
    amount_total = Column(Integer)
    currency = Column(String)
    needs_refund = Column(Boolean, nullable=False, default=True)
    refunded_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
