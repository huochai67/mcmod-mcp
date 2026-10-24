"""Rate-limited, retrying HTTP client for mcmod.cn SSR pages."""

from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass

import httpx

from .config import Settings
from .errors import NotFoundError, UpstreamError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetchResult:
    text: str
    url: str
    status_code: int


class RateLimiter:
    """Global minimum interval between requests, safe across threads."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = max(0.0, min_interval)
        self._lock = threading.Lock()
        self._last_request = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait_for = self._last_request + self.min_interval - now
            if wait_for > 0:
                time.sleep(wait_for)
            self._last_request = time.monotonic()


class McmodHttp:
    """Small wrapper around httpx with retries and politeness throttling."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._limiter = RateLimiter(settings.min_interval)
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(settings.timeout),
            follow_redirects=True,
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
            },
        )

    def close(self) -> None:
        self._client.close()

    def get(self, path: str, *, host: str = "main", params: dict | None = None) -> FetchResult:
        base = self.settings.search_url if host == "search" else self.settings.base_url
        url = base.rstrip("/") + "/" + path.lstrip("/")
        headers = {"Referer": self.settings.base_url + "/"} if host == "search" else None
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            self._limiter.wait()
            try:
                response = self._client.get(url, params=params, headers=headers)
                if response.status_code == 404:
                    raise NotFoundError(
                        f"mcmod page not found: {url}",
                        detail=f"HTTP 404 from {response.url}",
                    )
                if response.status_code == 429 or response.status_code >= 500:
                    delay = self._retry_delay(response, attempt)
                    logger.warning(
                        "upstream %s for %s (attempt %s/%s), retrying in %.1fs",
                        response.status_code,
                        response.url,
                        attempt + 1,
                        self.settings.max_retries + 1,
                        delay,
                    )
                    last_error = UpstreamError(
                        f"mcmod returned HTTP {response.status_code}",
                        detail=str(response.url),
                    )
                    time.sleep(delay)
                    continue
                if response.status_code >= 400:
                    raise UpstreamError(
                        f"mcmod returned HTTP {response.status_code}",
                        detail=str(response.url),
                    )
                # The site is UTF-8; be explicit in case a proxy drops the charset.
                if "charset" not in response.headers.get("content-type", "").lower():
                    response.encoding = "utf-8"
                return FetchResult(
                    text=response.text,
                    url=str(response.url),
                    status_code=response.status_code,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= self.settings.max_retries:
                    break
                delay = self._retry_delay(None, attempt)
                logger.warning(
                    "network error for %s (attempt %s/%s), retrying in %.1fs: %s",
                    url,
                    attempt + 1,
                    self.settings.max_retries + 1,
                    delay,
                    exc,
                )
                time.sleep(delay)
        raise UpstreamError(
            f"failed to fetch {url}",
            detail=str(last_error) if last_error else None,
        )

    def _retry_delay(self, response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return min(30.0, max(0.5, float(retry_after)))
                except ValueError:
                    pass
        return min(15.0, 0.6 * (2**attempt) + random.uniform(0, 0.35))
