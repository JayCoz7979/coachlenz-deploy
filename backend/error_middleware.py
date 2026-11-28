"""
Turn an unhandled exception into a JSON 500 that still carries CORS headers.

Starlette's ServerErrorMiddleware is the OUTERMOST layer, so an exception that
escapes a route skips CORSMiddleware on the way out. The browser then sees a bare
500 with no Access-Control-Allow-Origin and reports a misleading CORS failure
instead of the real error (exactly what happened to POST /live/report when the
report_type check rejected the insert).

This middleware is installed INSIDE CORSMiddleware (added before it in main.py,
since add_middleware makes the last-added layer outermost). It catches the
exception, reports it, and returns {"detail": "..."} so CORS decorates it like any
other response. No internals (trace, SQL, constraint names) reach the client.
"""
import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.observability import capture

logger = logging.getLogger(__name__)

INTERNAL_ERROR_DETAIL = "Something went wrong on our side. Please try again in a moment."


class JSONServerErrorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def _send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception as exc:  # noqa: BLE001 - last-resort handler by design
            logger.exception("Unhandled error on %s %s", scope.get("method"), scope.get("path"))
            capture(exc, path=str(scope.get("path")))
            if started:
                # Headers already went out; nothing safe to send. Let Starlette close it.
                raise
            response = JSONResponse({"detail": INTERNAL_ERROR_DETAIL}, status_code=500)
            await response(scope, receive, send)
