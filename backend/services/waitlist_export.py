"""Admin export of marketing_leads. No email is sent from here."""
import csv
import io
from datetime import datetime

from backend.services.waitlist_capture import nurture_eligible

COLUMNS = (
    "email",
    "first_name",
    "role",
    "role_branch",
    "is_adult",
    "school",
    "sport",
    "source",
    "lead_magnet",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "referrer",
    "landing_path",
    "ref_code",
    "consent_text_version",
    "confirmed_at",
    "unsubscribed_at",
    "has_account",
    "nurture_eligible",
    "created_at",
)


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = value.isoformat() if isinstance(value, datetime) else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        text = "'" + text
    return text


def leads_to_csv(rows) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow([
            _cell(nurture_eligible(row) if col == "nurture_eligible" else getattr(row, col, None))
            for col in COLUMNS
        ])
    return buf.getvalue()


def lead_to_dict(row) -> dict:
    out = {}
    for col in COLUMNS:
        if col == "nurture_eligible":
            out[col] = nurture_eligible(row)
            continue
        value = getattr(row, col, None)
        out[col] = value.isoformat() if isinstance(value, datetime) else value
    return out
