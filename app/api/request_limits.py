"""Bound streamed AI requests before FastAPI's JSON decoder allocates a tree."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.shared.request_limits import MAX_BODY_BYTES, MAX_JSON_DEPTH


AI_REQUEST_PATHS = frozenset({
    "/internal/v1/writing", "/internal/v1/page-composition",
    "/internal/v1/modification-planner", "/internal/v1/page-intent",
    "/internal/v1/intent", "/internal/v1/embeddings", "/internal/v1/page-question",
})


class AIRequestLimitsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].rstrip("/") not in AI_REQUEST_PATHS:
            await self.app(scope, receive, send)
            return

        body = bytearray()
        depth = 0
        in_string = escaped = False
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > MAX_BODY_BYTES:
                await self._reject(scope, receive, send)
                return
            for char in chunk:
                if in_string:
                    if escaped:
                        escaped = False
                    elif char == 92:  # backslash
                        escaped = True
                    elif char == 34:  # double quote
                        in_string = False
                elif char == 34:
                    in_string = True
                elif char in (91, 123):  # [ {
                    depth += 1
                    if depth > MAX_JSON_DEPTH:
                        await self._reject(scope, receive, send)
                        return
                elif char in (93, 125):  # ] }
                    depth -= 1
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        async def replay() -> dict:
            nonlocal body
            if body is not None:
                message = {"type": "http.request", "body": bytes(body), "more_body": False}
                body = None
                return message
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(status_code=422, content={"detail": [{
            "type": "value_error", "loc": ["body"],
            "msg": "AI request exceeds the body size or JSON nesting limit.",
        }]})
        await response(scope, receive, send)
