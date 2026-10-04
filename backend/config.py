from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    # Connection-pool sizing (Postgres only). The API runs `uvicorn --workers 4`
    # and there are ~7 worker services, so ~11 processes share ONE Postgres
    # (max_connections=100). Each process's ceiling is pool_size + max_overflow;
    # keep (processes x ceiling) comfortably under max_connections. Default ceiling
    # 7 -> ~77 worst-case, leaving headroom for migrate/admin. Raise DB_POOL_SIZE on
    # a specific service via env if it needs more concurrency (mind the math).
    DB_POOL_SIZE: int = 3
    DB_MAX_OVERFLOW: int = 4
    DB_POOL_TIMEOUT: int = 30      # seconds a request waits for a free connection
    DB_POOL_RECYCLE: int = 1800    # recycle a connection after 30 min (avoid stale)

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
    # User-facing film download/playback links. Kept short since a leaked URL is
    # valid for its whole lifetime; the app refreshes presigned URLs as needed, so
    # a viewing session never needs a week. (Detection uses its own 1-2h expiries.)
    R2_PRESIGNED_EXPIRY_SECONDS: int = 86400  # 24 hours

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    # Matches the model the report writer + AI-detect actually run in prod.
    # Override via env (ANTHROPIC_MODEL) to change the report model in one place.
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"

    # Detection verify tuning (COGS vs recall knob, deep mode). A merged play below
    # the confidence threshold (or flagged contradictory by the reconciler) gets an
    # Opus second look, capped per batch. Opus is ~69% of deep COGS, so LOWERING the
    # threshold (fewer plays verified) cuts cost but weakens made/miss correction;
    # tune against recall, never blind. Defaults preserve current behavior.
    DETECT_VERIFY_CONFIDENCE_THRESHOLD: float = 0.65
    DETECT_MAX_VERIFY_PER_BATCH: int = 3

    # Basketball frames-per-window (COGS vs recall knob). Basketball samples densely
    # because shots/steals happen in under a second; cost scales ~linearly with frames.
    # Env-tunable so a 120/100/80 same-game comparison can find the floor that holds
    # recall. Defaults preserve current behavior.
    DETECT_FRAMES_PER_WINDOW_BB_FAST: int = 120
    DETECT_FRAMES_PER_WINDOW_BB_DEEP: int = 100

    # Fast-path made/miss verify (accuracy fix without Opus). Fast mode skips the deep
    # verify pass, so uncertain shot RESULTS (e.g. paint makes that look like misses on a
    # single cam) go uncorrected. When enabled, one cheap Sonnet re-check per batch
    # re-reads the SAME (cached) frames for only the shaky shots and fixes made/miss,
    # never defaulting to "Missed". OFF by default: validate the cost add + the paint
    # made/miss gain on a test run before enabling.
    DETECT_FAST_RESULT_VERIFY: bool = False
    DETECT_FAST_RESULT_VERIFY_CONF: float = 0.75   # a shot at/below this confidence is re-checked
    DETECT_FAST_RESULT_VERIFY_MAX: int = 8         # cap re-checked shots per batch (cost guard)

    # Dead-time skip (basketball fast COGS lever). Basketball film is full of static
    # stretches — timeouts, huddles, dead balls, free-throw set-ups — that cost a full
    # vision call for no play. When enabled, each candidate window is scored locally by
    # inter-frame motion (no API cost) and clearly-static windows are skipped before they
    # are sent to Claude. OFF by default + fail-safe (a scoring error never skips a
    # window); validate the cost saving AND recall on a test run before enabling.
    DETECT_DEADTIME_SKIP: bool = False
    DETECT_DEADTIME_MOTION_MIN: float = 2.0   # mean abs 64x64 grayscale frame-diff below this = static

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    # Shared secret a monthly cron passes (?key=) to POST /admin/monthly-recap/run-due
    # so it can drive the recap sweep unattended. Empty = automation disabled (the
    # endpoint 403s), so the recap stays on-demand until Jay sets this.
    RECAP_CRON_SECRET: str = ""
    STRIPE_PRICE_COACH: str = ""
    STRIPE_PRICE_ATHLETIC_DEPT: str = ""
    STRIPE_PRICE_DISTRICT: str = ""
    # Annual (yearly-interval) Stripe price IDs. Leave empty and annual billing stays
    # dormant: the annual toggle never appears and /billing/checkout refuses annual with
    # a clear message. Set these to the yearly recurring price IDs and annual goes live
    # with NO code change. Annual grants the same tier + the same monthly included
    # allotment (reset monthly by the cron sweep, since a yearly invoice only fires once).
    STRIPE_PRICE_COACH_ANNUAL: str = ""
    STRIPE_PRICE_ATHLETIC_DEPT_ANNUAL: str = ""
    STRIPE_PRICE_DISTRICT_ANNUAL: str = ""

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
    # Shared rate-limit storage. The API runs with multiple uvicorn workers, and
    # slowapi's default in-memory storage is PER-PROCESS, so each worker keeps its
    # own counter and the effective limit is ~Nx (N = worker count). Point this at
    # the Railway Redis (redis://...) so all workers share ONE counter and limits
    # are enforced correctly. Empty = in-memory (single-worker / local dev). A
    # Redis outage degrades to in-memory, never blocks requests (see ratelimit.py).
    REDIS_URL: str = ""
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
    ADMIN_PASSWORD: str = ""  # set a strong 12+ char value in prod; seed.py refuses empty/weak

    # Default monthly analysis cap for a coach with NO explicit CoachUsageLimit row
    # (the base coach plan). Before this, an absent row meant UNLIMITED deep-Opus
    # runs — a leaked token or an eager coach could run up unbounded API cost. This
    # is a generous backstop, not a normal-use limit; set high enough to never bite
    # a real coach. An explicit CoachUsageLimit row (AD/district) still overrides it,
    # and an explicit 0 there still means unlimited. 0 here disables the backstop.
    DEFAULT_MONTHLY_ANALYSIS_LIMIT: int = 300

    # Row Level Security backstop (see docs/security/rls-backstop-plan.md).
    # When true, each transaction stamps the request/worker org into the Postgres
    # session GUC `app.org_id` so RLS policies can scope every query. DEFAULT FALSE:
    # the plumbing stays dormant until policies are in place AND the DATABASE_URL is
    # cut over from the `postgres` superuser (which bypasses RLS) to the restricted
    # `app_rls` role. Flip to true only per the staged rollout, never casually.
    RLS_ENABLED: bool = False

    # Duplicate-run financial control (#4). When true, a SECOND billable analysis on
    # film that was already analyzed returns a needs_confirmation signal instead of
    # silently charging again; the frontend confirms, then the confirmed re-run also
    # notifies all team coaches (CLAUDE.md financial control). DEFAULT FALSE so the
    # backend and frontend can deploy first; flip on once both are live. The
    # failure-refund half of #4 is always active and needs no flag.
    RERUN_CONFIRMATION_ENABLED: bool = False

    # Recruiting directory disclosure consent (#17). When true, minting a public
    # recruiting link requires the coach to accept the directory-disclosure
    # attestation for that player first (collected in the enable dialog). DEFAULT
    # FALSE so it ships dormant until the frontend checkbox is live; existing links
    # keep working (the gate is at mint time, never at serve time).
    RECRUITING_CONSENT_ENABLED: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
