"""CORS allow-list construction, isolated so it can be unit-tested without booting
the whole app. localhost is a DEV origin only: reflecting it in production (with
allow_credentials) would let any page on a developer's machine script the
authenticated API."""


def extra_allowed_origins(raw: str, environment: str) -> list[str]:
    """Exact origins from a comma-separated setting.

    Wildcards are dropped. Production accepts https only. Any other environment
    also accepts http, so a staging box can allow its own frontend. An empty
    string adds nothing, which keeps the historical allow-list.
    """
    found = []
    for piece in (raw or "").split(","):
        origin = piece.strip()
        if not origin or "*" in origin:
            continue
        if origin.startswith("https://"):
            found.append(origin)
        elif environment != "production" and origin.startswith("http://"):
            found.append(origin)
    return found


def build_allowed_origins(app_url: str, environment: str, extra_origins: str = "") -> list[str]:
    dev_origins = ["http://localhost:3000"] if environment != "production" else []
    origins = [
        app_url,
        "https://app.coachlenz.com",
        "https://coachlenz.com",
        "https://www.coachlenz.com",
        "https://coachlenz-frontend-production.up.railway.app",
        *dev_origins,
        *extra_allowed_origins(extra_origins, environment),
    ]
    # Dedupe (preserve order) and drop any falsy origin (e.g. an unset APP_URL).
    return [o for o in dict.fromkeys(origins) if o]
