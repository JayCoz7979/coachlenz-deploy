"""
Shared pytest fixtures + import-time environment for the CoachLenz backend suite.

`backend.config.Settings()` runs at import and REQUIRES DATABASE_URL and SECRET_KEY
(no defaults). conftest.py is imported by pytest before any test module, so setting
these here guarantees every `import backend.*` in a test resolves cleanly in CI
without real secrets. These are throwaway placeholders — never real credentials.
"""
import os

# Must be set BEFORE any `import backend.config` triggered by a test module.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/coachlenz_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-used-in-prod")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_placeholder")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_placeholder")
os.environ.setdefault("ENVIRONMENT", "test")
