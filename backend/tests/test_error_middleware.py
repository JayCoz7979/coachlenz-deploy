"""Unhandled errors must come back as JSON 500 WITH CORS headers.

Regression for the live_game report 500 (report_type check constraint): Starlette's
ServerErrorMiddleware sits outside CORSMiddleware, so the bare 500 had no
Access-Control-Allow-Origin and the browser reported a CORS failure instead of the
real error. backend.error_middleware.JSONServerErrorMiddleware fixes that.
"""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.error_middleware import JSONServerErrorMiddleware, GENERIC_500

pytestmark = pytest.mark.unit

ORIGIN = "https://app.coachlenz.com"


def _app():
    app = FastAPI()
    # Same order as backend/main.py: the JSON handler is added first (inner).
    app.add_middleware(JSONServerErrorMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=[ORIGIN], allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

    @app.post("/boom")
    async def boom():
        raise RuntimeError('new row violates check constraint "tendency_reports_report_type_check"')

    @app.post("/handled")
    async def handled():
        raise HTTPException(status_code=422, detail="Not enough plays")

    return app


def test_unhandled_error_is_json_with_cors_and_no_internals():
    c = TestClient(_app(), raise_server_exceptions=False)
    r = c.post("/boom", headers={"Origin": ORIGIN})
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers.get("access-control-allow-origin") == ORIGIN
    assert r.json() == GENERIC_500
    assert "constraint" not in r.text


def test_handled_errors_are_unchanged():
    c = TestClient(_app(), raise_server_exceptions=False)
    r = c.post("/handled", headers={"Origin": ORIGIN})
    assert r.status_code == 422
    assert r.json() == {"detail": "Not enough plays"}
    assert r.headers.get("access-control-allow-origin") == ORIGIN


def test_main_app_mounts_the_handler_inside_cors():
    # Read main.py instead of importing it (importing boots every worker module).
    # add_middleware prepends, so the one added FIRST ends up INSIDE the later ones.
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    json_at = src.index("app.add_middleware(JSONServerErrorMiddleware)")
    cors_at = src.index("CORSMiddleware,", src.index("app.add_middleware(\n"))
    assert json_at < cors_at
