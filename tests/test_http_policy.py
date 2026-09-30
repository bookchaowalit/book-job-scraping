"""PoliteHttp: per-host spacing, bounded retries, Retry-After, transport errors."""
import sys
import unittest
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from http_policy import HostUnavailable, PoliteHttp  # noqa: E402


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeTransport:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        status, headers = outcome
        return httpx.Response(status, headers=headers, request=httpx.Request("GET", url))


def make(outcomes, **kw):
    clock = FakeClock()
    transport = FakeTransport(outcomes)
    http = PoliteHttp(sleep=clock.sleep, clock=clock.clock, transport=transport, **kw)
    return http, transport, clock


class PoliteHttpTest(unittest.TestCase):
    def test_same_host_requests_are_spaced(self):
        http, _, clock = make([(200, {}), (200, {}), (200, {})], min_interval=2.0)
        http.get("https://a.io/1")
        http.get("https://a.io/2")
        http.get("https://b.io/1")  # other host: no wait
        self.assertEqual(clock.sleeps, [2.0])

    def test_retries_429_honouring_retry_after(self):
        http, transport, clock = make([(429, {"Retry-After": "7"}), (200, {})], min_interval=0)
        self.assertEqual(http.get("https://a.io").status_code, 200)
        self.assertEqual(len(transport.calls), 2)
        self.assertIn(7.0, clock.sleeps)
        self.assertEqual(http.stats["retries"], 1)

    def test_gives_back_last_response_after_max_attempts(self):
        http, transport, _ = make([(503, {})] * 3, min_interval=0, max_attempts=3)
        self.assertEqual(http.get("https://a.io").status_code, 503)
        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(http.stats["failures"], 1)

    def test_non_retryable_status_returns_immediately(self):
        http, transport, _ = make([(404, {})], min_interval=0)
        self.assertEqual(http.get("https://a.io").status_code, 404)
        self.assertEqual(len(transport.calls), 1)

    def test_transport_error_retried_then_raised(self):
        err = httpx.ConnectError("down")
        http, transport, _ = make([err, err], min_interval=0, max_attempts=2)
        with self.assertRaises(httpx.ConnectError):
            http.get("https://a.io")
        self.assertEqual(len(transport.calls), 2)

    def test_retry_after_is_capped(self):
        http, _, clock = make([(429, {"Retry-After": "3600"}), (200, {})], min_interval=0)
        http.get("https://a.io")
        self.assertIn(60.0, clock.sleeps)

    def test_failed_host_is_skipped_for_rest_of_run(self):
        err = httpx.ReadTimeout("slow")
        http, transport, _ = make([err, err, (200, {})], min_interval=0, max_attempts=2)
        with self.assertRaises(httpx.ReadTimeout):
            http.get("https://dead.io/a")
        with self.assertRaises(HostUnavailable):
            http.get("https://dead.io/b")
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(http.get("https://alive.io").status_code, 200)
        self.assertEqual(http.stats["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
