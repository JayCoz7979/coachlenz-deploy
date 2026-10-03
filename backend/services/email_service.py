import resend
from backend.config import settings

resend.api_key = settings.RESEND_API_KEY
FROM = f"CoachLenz <noreply@{settings.RESEND_DOMAIN}>"
# The welcome email comes from Jay personally, not a no-reply. Same verified
# sending domain (so it delivers), but a founder From + a real reply-to.
FOUNDER_FROM = f"Jay Cosby, CoachLenz <jay@{settings.RESEND_DOMAIN}>"
FOUNDER_REPLY_TO = settings.FOUNDER_REPLY_TO or f"jay@{settings.RESEND_DOMAIN}"

async def send_welcome_email(to: str, name: str):
    first = (name or "Coach").split(" ")[0]
    resend.Emails.send({
        "from": FOUNDER_FROM,
        "reply_to": FOUNDER_REPLY_TO,
        "to": to,
        "subject": "Welcome to CoachLenz",
        "html": (
            f"<p>Hey {first},</p>"
            f"<p>Jay here, the founder of CoachLenz. I wanted to welcome you myself.</p>"
            f"<p>You didn't sign up for another dashboard. You signed up to get your nights back. "
            f"CoachLenz watches the film, finds the tendencies, and hands you the game plan, so your "
            f"time goes to coaching instead of scrubbing tape.</p>"
            f"<p>Upload a game, let the AI tag it, and generate your first report. If you get stuck or "
            f"have an idea, just reply to this email. It reaches me.</p>"
            f"<p>Let's get to work,<br/>Jay Cosby<br/>Founder, CoachLenz</p>"
            f"<p style='color:#666;font-size:12px'>Powered by "
            f"<a href='https://cosbyaisolutions.com'>Cosby AI Solutions</a></p>"
        ),
    })

async def send_trial_ending_email(to: str, name: str, days_left: int):
    resend.Emails.send({
        "from": FROM,
        "to": to,
        "subject": f"Your CoachLenz trial ends in {days_left} day{'s' if days_left != 1 else ''}",
        "html": f"<p>Hi {name},</p><p>Your trial ends in {days_left} day{'s' if days_left != 1 else ''}. Upgrade to keep full access.</p><p>Powered by <a href='https://cosbyaisolutions.com'>Cosby AI Solutions</a></p>",
    })

async def send_report_ready_email(to: str, name: str, report_title: str, report_url: str):
    resend.Emails.send({
        "from": FROM,
        "to": to,
        "subject": f"Your report is ready: {report_title}",
        "html": f"<p>Hi {name},</p><p>Your tendency report <strong>{report_title}</strong> is ready.</p><p><a href='{report_url}'>View Report</a></p><p>Powered by <a href='https://cosbyaisolutions.com'>Cosby AI Solutions</a></p>",
    })

async def send_report_failure_alert(to: str, report_title: str, reason: str):
    """Ops alert to the founder/admin when report generation fails (e.g. the Anthropic
    usage limit). Internal, not customer-facing; caller best-efforts the send. The
    coach only ever sees a generic message, so this is where the real reason surfaces."""
    import html as _html
    resend.Emails.send({
        "from": FOUNDER_FROM,
        "reply_to": FOUNDER_REPLY_TO,
        "to": to,
        "subject": f"[CoachLenz] Report generation failing: {report_title}",
        "html": (
            f"<p>A scouting report failed to generate.</p>"
            f"<p><b>Report:</b> {_html.escape(report_title or '')}</p>"
            f"<p><b>Reason:</b> {_html.escape(reason or '')}</p>"
            f"<p>If this is an API usage limit, raise or top up the limit in the Anthropic Console "
            f"for the CoachLenz production API key. Coaches are shown a generic "
            f"&ldquo;try again in a few minutes&rdquo; message until this clears.</p>"
        ),
    })


async def send_email_verification_code(to: str, name: str, code: str):
    resend.Emails.send({
        "from": FROM,
        "to": to,
        "subject": f"Your CoachLenz verification code: {code}",
        "html": (
            f"<p>Hi {name},</p>"
            f"<p>Enter this code to verify your email and continue setting up CoachLenz:</p>"
            f"<p style='font-size:30px;font-weight:800;letter-spacing:6px;margin:16px 0'>{code}</p>"
            f"<p style='color:#666;font-size:13px'>This code expires in 15 minutes. If you didn't start a "
            f"CoachLenz sign-up, you can ignore this email.</p>"
            f"<p>Powered by <a href='https://cosbyaisolutions.com'>Cosby AI Solutions</a></p>"
        ),
    })


async def send_password_reset_email(to: str, name: str, reset_url: str):
    resend.Emails.send({
        "from": FROM,
        "to": to,
        "subject": "Reset your CoachLenz password",
        "html": (
            f"<p>Hi {name},</p>"
            f"<p>We received a request to reset your CoachLenz password. "
            f"Click the button below to choose a new one. This link expires in 1 hour "
            f"and can be used once.</p>"
            f"<p><a href='{reset_url}' style='display:inline-block;background:#1a5c2a;color:#fff;"
            f"padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:600'>Reset Password</a></p>"
            f"<p style='color:#666;font-size:13px'>If you didn't request this, you can safely ignore "
            f"this email — your password will not change.</p>"
            f"<p>Powered by <a href='https://cosbyaisolutions.com'>Cosby AI Solutions</a></p>"
        ),
    })


async def send_staff_invite_email(to: str, name: str, inviter_name: str, org_name: str, invite_url: str):
    resend.Emails.send({
        "from": FROM,
        "to": to,
        "subject": f"You've been added to {org_name} on CoachLenz",
        "html": (
            f"<p>Hi {name},</p>"
            f"<p>{inviter_name} added you to <strong>{org_name}</strong>'s staff on CoachLenz. "
            f"Click below to set your password and get started. This invite expires in 7 days.</p>"
            f"<p><a href='{invite_url}' style='display:inline-block;background:#1a5c2a;color:#fff;"
            f"padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:600'>Accept Invite</a></p>"
            f"<p style='color:#666;font-size:13px'>If you weren't expecting this, you can ignore this email.</p>"
            f"<p>Powered by <a href='https://cosbyaisolutions.com'>Cosby AI Solutions</a></p>"
        ),
    })


async def send_recruiting_profile_email(to: str, player_name: str, coach_name: str, org_name: str, profile_url: str):
    resend.Emails.send({
        "from": FROM,
        "to": to,
        "subject": f"Recruiting profile: {player_name} ({org_name})",
        "html": (
            f"<p>Hi,</p>"
            f"<p>{coach_name} from <strong>{org_name}</strong> shared a recruiting profile "
            f"for <strong>{player_name}</strong> with you on CoachLenz — highlights and "
            f"key details, no login required.</p>"
            f"<p><a href='{profile_url}' style='display:inline-block;background:#1a5c2a;color:#fff;"
            f"padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:600'>View Profile</a></p>"
            f"<p style='color:#666;font-size:13px'>This link expires on the date set by the coach.</p>"
            f"<p>Powered by <a href='https://cosbyaisolutions.com'>Cosby AI Solutions</a></p>"
        ),
    })


async def send_referral_credit_email(to: str, name: str, credit_amount: str):
    resend.Emails.send({
        "from": FROM,
        "to": to,
        "subject": "You earned a referral credit!",
        "html": f"<p>Hi {name},</p><p>Great news — you earned a <strong>{credit_amount}</strong> credit for referring a new CoachLenz customer.</p><p>Powered by <a href='https://cosbyaisolutions.com'>Cosby AI Solutions</a></p>",
    })


async def send_monthly_recap_email(to: str, subject: str, html: str):
    """Monthly recap (F3). Sent from the founder address so a reply reaches Jay, and
    so the per-cycle 'here is what CoachLenz did for you' win feels personal."""
    resend.Emails.send({
        "from": FOUNDER_FROM,
        "reply_to": FOUNDER_REPLY_TO,
        "to": to,
        "subject": subject,
        "html": html,
    })


# ── COPPA/FERPA privacy requests ───────────────────────────────────────────────
PRIVACY_REPLY_TO = f"privacy@{settings.RESEND_DOMAIN}"


async def send_privacy_request_ack(to: str, name: str, request_type: str, reference: str):
    """Acknowledge a parent's data access/deletion request so they know it was received."""
    first = (name or "there").split(" ")[0]
    label = "deletion" if request_type == "deletion" else "access"
    resend.Emails.send({
        "from": FROM,
        "reply_to": PRIVACY_REPLY_TO,
        "to": to,
        "subject": "We received your CoachLenz data request",
        "html": (
            f"<p>Hi {first},</p>"
            f"<p>We received your request to <strong>{label}</strong> a student-athlete's data in "
            f"CoachLenz. Your reference is <strong>{reference}</strong>.</p>"
            f"<p>To protect students, we verify every request before acting on it, in coordination "
            f"with the school when needed. We'll email you when it's complete. Most requests are "
            f"handled within 14 days.</p>"
            f"<p>Questions: just reply to this email (privacy@coachlenz.com).</p>"
            f"<p style='color:#666;font-size:12px'>Powered by "
            f"<a href='https://cosbyaisolutions.com'>Cosby AI Solutions</a></p>"
        ),
    })


async def send_privacy_admin_notice(to: str, request):
    """Alert the CoachLenz admin that a new privacy request needs review."""
    resend.Emails.send({
        "from": FROM,
        "to": to,
        "subject": f"New {request.request_type} privacy request — {request.student_name}",
        "html": (
            f"<p>A new <strong>{request.request_type}</strong> request was submitted.</p>"
            f"<ul>"
            f"<li>Requester: {request.requester_name} ({request.relationship}) — {request.requester_email}</li>"
            f"<li>Student: {request.student_name}</li>"
            f"<li>School/org: {request.school_or_org or '(not given)'}</li>"
            f"<li>Details: {request.student_details or ''} {request.details or ''}</li>"
            f"<li>Reference: {request.id}</li>"
            f"</ul>"
            f"<p>Review it in the admin Privacy Requests page: verify the requester, then fulfill or reject.</p>"
        ),
    })


async def send_deletion_certificate(to: str, name: str, certificate_html: str):
    """Send the parent the Deletion Certificate when a deletion request is completed."""
    first = (name or "there").split(" ")[0]
    resend.Emails.send({
        "from": FROM,
        "reply_to": PRIVACY_REPLY_TO,
        "to": to,
        "subject": "Your CoachLenz data deletion is complete",
        "html": (
            f"<p>Hi {first},</p>"
            f"<p>Your request is complete. Your Deletion Certificate is below.</p>"
            f"<hr/>{certificate_html}"
        ),
    })


async def send_privacy_request_resolution(to: str, name: str, subject: str, message_html: str):
    """Generic completion/rejection notice for an access request or a rejected request."""
    first = (name or "there").split(" ")[0]
    resend.Emails.send({
        "from": FROM,
        "reply_to": PRIVACY_REPLY_TO,
        "to": to,
        "subject": subject,
        "html": (
            f"<p>Hi {first},</p>{message_html}"
            f"<p>Questions: just reply to this email (privacy@coachlenz.com).</p>"
            f"<p style='color:#666;font-size:12px'>Powered by "
            f"<a href='https://cosbyaisolutions.com'>Cosby AI Solutions</a></p>"
        ),
    })
