"""CORS allow-list construction, isolated so it can be unit-tested without booting
the whole app. localhost is a DEV origin only: reflecting it in production (with
allow_credentials) would let any page on a developer's machine script the
authenticated API."""


def build_allowed_origins(app_url: str, environment: str) -> list[str]:
    dev_origins = ["http://localhost:3000"] if environment != "production" else []
    origins = [
        app_url,
        "https://app.coachlenz.com",
        "https://coachlenz.com",
        "https://www.coachlenz.com",
        "https://coachlenz-frontend-production.up.railway.app",
        *dev_origins,
    ]
    # Dedupe (preserve order) and drop any falsy origin (e.g. an unset APP_URL).
    return [o for o in dict.fromkeys(origins) if o]
