"""Admin export of marketing_leads. No email is sent from here."""
import csv
import io
from datetime import datetime

COLUMNS = (
    "email",
    "name",
    "role",
    "role_other",
    "school",
    "sport",
    "source",
    "lead_magnet",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "email_consent_at",
    "email_consent_version",
    "created_at",
)


def _cell(value) -> str:
    if value is None:
        return ""
    text = value.isoformat() if isinstance(value, datetime) else str(value)
    # Stop a spreadsheet from treating a cell as a formula.
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        text = "'" + text
    return text


def leads_to_csv(rows) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow([_cell(getattr(row, col, None)) for col in COLUMNS])
    return buf.getvalue()


def lead_to_dict(row) -> dict:
    out = {}
    for col in COLUMNS:
        value = getattr(row, col, None)
        out[col] = value.isoformat() if isinstance(value, datetime) else value
    return out
