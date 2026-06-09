from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Auth
    SECRET_KEY: str
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
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5"

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

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_VERIFY_SID: str = ""

    # Sentry
    SENTRY_DSN: Optional[str] = None

    # App
    APP_URL: str = "https://coachlenz.com"
    ENVIRONMENT: str = "production"
    MAX_UPLOAD_BYTES: int = 21474836480  # 20GB
    TRIAL_DAYS: int = 14
    TRIAL_GAME_LIMIT: int = 1

    # Encryption
    FERNET_KEY: str = ""

    # Admin
    ADMIN_PASSWORD: str = "ChangeMeNow!"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
