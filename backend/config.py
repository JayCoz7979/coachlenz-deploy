from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Auth
    SECRET_KEY: str
    # Grace-window key rotation: set this to the OLD SECRET_KEY when you rotate.
    # New tokens are signed with SECRET_KEY; decode_token still accepts tokens
    # signed with SECRET_KEY_PREVIOUS so no one is logged out mid-rotation. Drop it
    # after the refresh-token lifetime (30 days) has elapsed. See
    # CREDENTIAL_ROTATION_SCHEDULE.md.
    SECRET_KEY_PREVIOUS: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Cloudflare R2
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = "coachlenz-film"
    R2_ENDPOINT_URL: str = ""
    R2_PRESIGNED_EXPIRY_SECONDS: int = 604800  # 7 days

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    # Matches the model the report writer + AI-detect actually run in prod.
    # Override via env (ANTHROPIC_MODEL) to change the report model in one place.
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_COACH: str = ""
    STRIPE_PRICE_ATHLETIC_DEPT: str = ""
    STRIPE_PRICE_DISTRICT: str = ""

    # Resend
    RESEND_API_KEY: str = ""
    RESEND_DOMAIN: str = "cosbyaisolutions.com"
    EMAIL_FROM: str = "CoachLenz <noreply@cosbyaisolutions.com>"
    ADMIN_EMAIL: str = "info@cosbyaisolutions.com"
    # Comma-separated allowlist of platform super-admin emails. This is the ONLY
    # thing (besides an org's admin_level) that unlocks the /admin/* surface, which
    # can edit ANY org's plan/entitlements. Default empty = no email is admin until
    # set. e.g. ADMIN_EMAILS="aiwithjaycoz@gmail.com".
    ADMIN_EMAILS: str = ""
    # Where replies to the founder welcome email land. Empty -> jay@<RESEND_DOMAIN>.
    # Set this env to a monitored inbox (e.g. a Gmail) so "just reply" actually reaches Jay.
    FOUNDER_REPLY_TO: str = ""

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_VERIFY_SID: str = ""

    # Sentry
    SENTRY_DSN: Optional[str] = None

    # Which workers the API process runs in-process, alongside serving HTTP.
    #   "all"  (default) - every worker; matches historical behavior.
    #   "light"          - skip the OOM/CPU-heavy workers (ai_detect, ingest) so a
    #                      crash in a big detection job can't take the API down.
    #                      Set this once the dedicated worker service handles them.
    #   "none"           - API serves HTTP only; all jobs run on worker services.
    WORKERS_IN_API: str = "all"

    # App
    APP_URL: str = "https://coachlenz.com"
    ENVIRONMENT: str = "production"
    MAX_UPLOAD_BYTES: int = 21474836480  # 20GB
    TRIAL_DAYS: int = 14
    TRIAL_GAME_LIMIT: int = 1

    # Encryption
    FERNET_KEY: str = ""
    # Grace-window key rotation: comma-separated OLD Fernet keys. Data is encrypted
    # with FERNET_KEY (the new primary) but decrypted against FERNET_KEY + these, so
    # rotating the key never orphans already-encrypted data. Drop an old key once all
    # data has been re-encrypted. See CREDENTIAL_ROTATION_SCHEDULE.md.
    FERNET_KEYS_PREVIOUS: str = ""

    # Admin
    ADMIN_PASSWORD: str = "ChangeMeNow!"

    # Row Level Security backstop (see docs/security/rls-backstop-plan.md).
    # When true, each transaction stamps the request/worker org into the Postgres
    # session GUC `app.org_id` so RLS policies can scope every query. DEFAULT FALSE:
    # the plumbing stays dormant until policies are in place AND the DATABASE_URL is
    # cut over from the `postgres` superuser (which bypasses RLS) to the restricted
    # `app_rls` role. Flip to true only per the staged rollout, never casually.
    RLS_ENABLED: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
