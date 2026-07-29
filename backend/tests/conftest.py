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

# test_api_integration.py is a helper SCRIPT (exposes run(), has no test_* funcs)
# that hard-imports aiosqlite at module load. pytest imports every test file during
# COLLECTION to read markers, so collecting it directly would import aiosqlite even
# in the unit job (which doesn't install it) and crash collection before the
# integration marker can deselect anything. It is driven instead via the
# integration-marked bridge in test_legacy_suite.py, so exclude it from direct
# collection in every job. The bridge still imports it lazily where aiosqlite exists.
collect_ignore = ["test_api_integration.py"]

