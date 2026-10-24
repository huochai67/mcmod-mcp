"""Shared API-key authentication for the REST API and MCP HTTP endpoint."""

from __future__ import annotations

import json
import secrets

from starlette.types import ASGIApp, Receive, Scope, Send

_UNAUTHORIZED_BODY = json.dumps(
    {"error": {"code": "unauthorized", "message": "invalid or missing API key"}},
    separators=(",", ":"),
).encode()


def _presented_keys(headers: list[tuple[bytes, bytes]]) -> list[str]:
    keys: list[str] = []
    for name, value in headers:
        if name == b"authorization":
            scheme, _, token = value.decode("latin-1").partition(" ")
            if scheme.lower() == "bearer" and token:
                keys.append(token.strip())
        elif name == b"x-api-key":
            token = value.decode("latin-1").strip()
            if token:
                keys.append(token)
    return keys


class ApiKeyMiddleware:
    """Require one shared key for every HTTP request except health/docs.

    ``Authorization: Bearer <key>`` and ``X-API-Key: <key>`` are both accepted.
    An empty key disables authentication for local development.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        api_key: str,
        exempt_paths: tuple[str, ...] = ("/health", "/openapi.json"),
        exempt_prefixes: tuple[str, ...] = ("/docs", "/redoc"),
    ) -> None:
        self.app = app
        self.api_key = api_key
        self.exempt_paths = frozenset(exempt_paths)
        self.exempt_prefixes = tuple(exempt_prefixes)

    def _exempt(self, path: str) -> bool:
        if path in self.exempt_paths:
            return True
        return any(path == prefix or path.startswith(prefix + "/") for prefix in self.exempt_prefixes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.api_key or self._exempt(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        keys = _presented_keys(scope.get("headers", []))
        if any(secrets.compare_digest(key, self.api_key) for key in keys):
            await self.app(scope, receive, send)
            return

        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_UNAUTHORIZED_BODY)).encode()),
                    (b"www-authenticate", b'Bearer realm="mcmod"'),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _UNAUTHORIZED_BODY})
