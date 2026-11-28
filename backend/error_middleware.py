"""
Turn an unhandled exception into a JSON 500 INSIDE the CORS middleware.

Starlette's ServerErrorMiddleware is the outermost layer, so a bare unhandled
exception (e.g. the live_game report INSERT that violated
tendency_reports_report_type_check) was answered as a plain-text 500 that never
passed back through CORSMiddleware. The browser then hid the real status behind a
CORS error. Mounting this ASGI middleware just inside CORSMiddleware means real
errors still come back as JSON, with the CORS headers the app needs to read them.

The exception is logged and reported to Sentry; the response body never echoes
internals (no stack traces, SQL, or constraint names).
"""
import json
import logging

logger = logging.getLogger(__name__)

GENERIC_500 = {"detail": "Something went wrong on our side. Please try again."}


class JSONServerErrorMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
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
        except Exception as exc:  # noqa: BLE001 - last-resort handler, re-raised if unsendable
            logger.exception("Unhandled error on %s %s", scope.get("method"), scope.get("path"))
            try:
                from backend.observability import capture
                capture(exc, path=str(scope.get("path")))
            except Exception:  # pragma: no cover - observability must never mask the error
                pass
            if started:
                # Headers already went out; nothing safe to send. Let the server close it.
                raise
            body = json.dumps(GENERIC_500).encode()
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())],
            })
            await send({"type": "http.response.body", "body": body})
