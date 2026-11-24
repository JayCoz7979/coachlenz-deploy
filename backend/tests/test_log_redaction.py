"""N2: signed URL query strings never reach the backend logs."""
import logging

import pytest

from backend import log_redaction


@pytest.mark.unit
def test_access_log_line_keeps_path_and_status_but_drops_the_signature():
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d',
        ("203.0.113.8:0", "PUT", "/files/multipart/abc123/2?sig=eyJhbGciOi.secret.part", "1.1", 200),
        None,
    )
    assert log_redaction.RedactSignedQueryFilter().filter(record) is True
    line = record.getMessage()
    assert "/files/multipart/abc123/2?[redacted]" in line
    assert "eyJhbGciOi" not in line and "secret" not in line
    assert line.endswith(" 200")


@pytest.mark.unit
@pytest.mark.parametrize("url,secret", [
    ("/x?X-Amz-Signature=abc111&X-Amz-Credential=k", "abc111"),
    ("/files/a?exp=1&sig=zzz222", "zzz222"),
    ("/u?upload_token=tok333", "tok333"),
    ("https://r2.example.com/bucket/key?X-Amz-Security-Token=t444", "t444"),
])
def test_sensitive_queries_are_redacted(url, secret):
    out = log_redaction.redact_text(f"GET {url} 200")
    assert "?[redacted] 200" in out
    assert secret not in out


@pytest.mark.unit
def test_harmless_queries_and_plain_paths_are_untouched():
    for text in ("GET /games?page=2&sport=football 200", "GET /health 200", "no url here?", 42, None):
        assert log_redaction.redact_text(text) == text


@pytest.mark.unit
def test_install_is_idempotent_and_targets_uvicorn_loggers():
    log_redaction.install()
    log_redaction.install()
    access = logging.getLogger("uvicorn.access")
    assert sum(isinstance(f, log_redaction.RedactSignedQueryFilter) for f in access.filters) == 1
