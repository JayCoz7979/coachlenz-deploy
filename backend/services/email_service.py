import resend
from backend.config import settings

resend.api_key = settings.RESEND_API_KEY
FROM = f"CoachLenz <noreply@{settings.RESEND_DOMAIN}>"

async def send_welcome_email(to: str, name: str):
    resend.Emails.send({
        "from": FROM,
        "to": to,
        "subject": "Welcome to CoachLenz",
        "html": f"<p>Hi {name},</p><p>Welcome to CoachLenz — your AI-powered film analysis platform.</p><p>Powered by <a href='https://cosbyaisolutions.com'>Cosby AI Solutions</a></p>",
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
