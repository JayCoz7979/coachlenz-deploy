from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str

    # Auth
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "coachlenz-film"
    r2_endpoint_url: str = ""
    r2_presigned_expiry_seconds: int = 604800  # 7 days

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_coach: str = ""
    stripe_price_athletic_dept: str = ""
    stripe_price_district: str = ""

    # Resend
    resend_api_key: str = ""
    resend_domain: str = "cosbyaisolutions.com"
    email_from: str = "CoachLenz <noreply@cosbyaisolutions.com>"
    admin_email: str = "info@cosbyaisolutions.com"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_verify_sid: str = ""

    # Sentry
    sentry_dsn: Optional[str] = None

    # App
    app_url: str = "https://coachlenz.com"
    environment: str = "production"
    max_upload_bytes: int = 21474836480  # 20GB
    trial_days: int = 14
    trial_game_limit: int = 1

    # Encryption
    fernet_key: str = ""

    # Admin
    admin_password: str = "ChangeMeNow!"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
