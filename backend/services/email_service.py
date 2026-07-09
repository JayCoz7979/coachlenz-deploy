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


async def send_referral_credit_email(to: str, name: str, credit_amount: str):
    resend.Emails.send({
        "from": FROM,
        "to": to,
        "subject": "You earned a referral credit!",
        "html": f"<p>Hi {name},</p><p>Great news — you earned a <strong>{credit_amount}</strong> credit for referring a new CoachLenz customer.</p><p>Powered by <a href='https://cosbyaisolutions.com'>Cosby AI Solutions</a></p>",
    })
