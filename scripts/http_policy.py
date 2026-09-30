#!/usr/bin/env python3
"""Polite HTTP access for board fetchers: per-host spacing plus bounded retries.

Drop-in for ``httpx.get``/``httpx.post``: returns the final ``httpx.Response``
(callers keep checking ``status_code``) and re-raises the last transport error
when every attempt failed.

A host whose request exhausts every attempt is marked down for the rest of the
run (circuit breaker): later calls to it raise ``HostUnavailable`` immediately
instead of paying the timeouts again for each keyword.
"""
from __future__ import annotations

import threading
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_AFTER_SECONDS = 60.0


class HostUnavailable(httpx.TransportError):
    """Raised without a request when the host already failed in this run."""


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After", "").strip()
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


class PoliteHttp:
    def __init__(
        self,
        *,
        min_interval: float = 1.0,
        max_attempts: int = 3,
        backoff_base: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        transport: Any = httpx,
    ):
        self.min_interval = min_interval
        self.max_attempts = max(1, max_attempts)
        self.backoff_base = backoff_base
        self._sleep = sleep
        self._clock = clock
        self._transport = transport
        self._lock = threading.Lock()
        self._next_allowed: dict[str, float] = {}
        self._down_hosts: set[str] = set()
        self.stats = {"requests": 0, "retries": 0, "failures": 0, "skipped": 0}

    def _wait_for_host(self, url: str) -> None:
        host = urlsplit(url).netloc.lower()
        with self._lock:
            now = self._clock()
            ready_at = self._next_allowed.get(host, now)
            wait = max(0.0, ready_at - now)
            self._next_allowed[host] = max(now, ready_at) + self.min_interval
        if wait:
            self._sleep(wait)

    @property
    def down_hosts(self) -> set[str]:
        return set(self._down_hosts)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        host = urlsplit(url).netloc.lower()
        if host in self._down_hosts:
            self.stats["skipped"] += 1
            raise HostUnavailable(f"{host} failed earlier in this run; skipping")
        call = getattr(self._transport, method)
        last_error: Exception | None = None
        response: httpx.Response | None = None
        for attempt in range(1, self.max_attempts + 1):
            self._wait_for_host(url)
            self.stats["requests"] += 1
            try:
                response = call(url, **kwargs)
                last_error = None
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error, response = exc, None
            if response is not None and response.status_code not in RETRY_STATUSES:
                return response
            if attempt == self.max_attempts:
                break
            delay = self.backoff_base ** attempt
            if response is not None:
                hinted = _retry_after_seconds(response)
                if hinted is not None:
                    delay = min(hinted, MAX_RETRY_AFTER_SECONDS)
            self.stats["retries"] += 1
            self._sleep(delay)
        self.stats["failures"] += 1
        self._down_hosts.add(host)
        if response is not None:
            return response
        assert last_error is not None
        raise last_error

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("get", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("post", url, **kwargs)
