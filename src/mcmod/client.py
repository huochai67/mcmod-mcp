"""HTTP client for the mcmod REST API, used by the CLI and MCP server."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .errors import ApiClientError


class McmodApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            headers={"Accept": "application/json"},
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        query = {key: value for key, value in (params or {}).items() if value not in (None, "")}
        if refresh:
            query["refresh"] = "true"
        return self._request("GET", path, params=query)

    def post(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", path, params=params)

    def delete(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("DELETE", path, params=params)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = self._client.request(method, path, params=params, headers=headers)
        except httpx.ConnectError as exc:
            raise ApiClientError(
                f"cannot connect to mcmod API at {self.base_url}; start it with `mcmod serve`",
                code="connection_error",
                detail=str(exc),
            ) from exc
        except httpx.TimeoutException as exc:
            raise ApiClientError(
                f"mcmod API request timed out: {method} {path}",
                code="timeout",
                detail=str(exc),
            ) from exc
        except httpx.HTTPError as exc:
            raise ApiClientError(
                f"mcmod API request failed: {method} {path}",
                code="transport_error",
                detail=str(exc),
            ) from exc

        try:
            payload = response.json()
        except ValueError:
            payload = None
        if response.status_code >= 400:
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict):
                detail = error.get("detail")
                if detail is not None and not isinstance(detail, str):
                    detail = json.dumps(detail, ensure_ascii=False)
                raise ApiClientError(
                    str(error.get("message") or response.reason_phrase),
                    status_code=response.status_code,
                    code=str(error.get("code") or "api_error"),
                    detail=detail,
                )
            raise ApiClientError(
                response.text or response.reason_phrase,
                status_code=response.status_code,
            )
        if not isinstance(payload, dict):
            raise ApiClientError(
                "mcmod API returned a non-JSON response",
                status_code=response.status_code,
                code="invalid_response",
            )
        return payload
