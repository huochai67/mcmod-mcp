"""Domain errors shared by API, service and clients."""

from __future__ import annotations


class McmodError(RuntimeError):
    code = "mcmod_error"
    status_code = 500

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class NotFoundError(McmodError):
    code = "not_found"
    status_code = 404


class InvalidRequestError(McmodError):
    code = "invalid_request"
    status_code = 400


class UpstreamError(McmodError):
    code = "upstream_error"
    status_code = 502


class ParseError(McmodError):
    code = "parse_error"
    status_code = 502


class CacheUnavailableError(McmodError):
    code = "cache_unavailable"
    status_code = 503


class AuthenticationError(McmodError):
    code = "unauthorized"
    status_code = 401


class ApiClientError(McmodError):
    """Raised by the HTTP API client used by the CLI and MCP server."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        code: str = "api_error",
        detail: str | None = None,
    ) -> None:
        super().__init__(message, detail=detail)
        self.status_code = status_code
        self.code = code
