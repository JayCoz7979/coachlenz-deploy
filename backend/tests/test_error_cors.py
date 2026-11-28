"""
An unhandled exception must come back as a JSON 500 that still carries CORS
headers. Before the fix, POST /live/report's 500 (the report_type check) escaped
CORSMiddleware, so the browser showed a misleading CORS error instead of the real
failure. The middleware must sit INSIDE CORSMiddleware in the real app.
"""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.error_middleware import INTERNAL_ERROR_DETAIL, JSONServerErrorMiddleware

pytestmark = pytest.mark.unit

ORIGIN = "https://app.coachlenz.com"


def _app():
    app = FastAPI()

    @app.post("/boom")
    async def boom():
        raise RuntimeError('insert violates check constraint "tendency_reports_report_type_check"')

    @app.post("/handled")
    async def handled():
        raise HTTPException(status_code=422, detail="Not enough plays logged yet.")

    # Same order as backend/main.py: error middleware first (inner), CORS outside it.
    app.add_middleware(JSONServerErrorMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=[ORIGIN], allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    return app


def test_unhandled_error_is_json_500_with_cors():
    c = TestClient(_app(), raise_server_exceptions=False)
    r = c.post("/boom", headers={"Origin": ORIGIN})
    assert r.status_code == 500
    assert r.json() == {"detail": INTERNAL_ERROR_DETAIL}
    assert r.headers.get("access-control-allow-origin") == ORIGIN
    # No internals leak to the client.
    assert "constraint" not in r.text and "tendency_reports" not in r.text


def test_handled_errors_are_unchanged():
    c = TestClient(_app(), raise_server_exceptions=False)
    r = c.post("/handled", headers={"Origin": ORIGIN})
    assert r.status_code == 422
    assert r.json() == {"detail": "Not enough plays logged yet."}
    assert r.headers.get("access-control-allow-origin") == ORIGIN


def test_real_app_installs_error_middleware_inside_cors():
    from backend.main import app

    classes = [m.cls for m in app.user_middleware]   # index 0 = outermost
    assert JSONServerErrorMiddleware in classes
    assert classes.index(CORSMiddleware) < classes.index(JSONServerErrorMiddleware)


def test_real_app_exposes_the_live_tracker_paywall_header():
    from backend.main import app

    cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
    assert "X-CoachLenz-Locked" in cors.kwargs.get("expose_headers", [])
