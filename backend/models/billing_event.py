from datetime import datetime

from sqlalchemy import Column, String, DateTime

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
