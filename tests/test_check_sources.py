from __future__ import annotations

import sys
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import check_sources


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://example.test/a.pdf", code, "x", headers, None)


class RetryDelayTest(unittest.TestCase):
    def test_rate_limit_uses_retry_after_capped(self) -> None:
        self.assertEqual(check_sources._retry_delay(_http_error(429, "30"), 0), 30.0)
        self.assertEqual(
            check_sources._retry_delay(_http_error(429, "9999"), 0),
            float(check_sources.MAX_RETRY_AFTER_SECONDS),
        )

    def test_rate_limit_without_header_backs_off_long(self) -> None:
        self.assertEqual(check_sources._retry_delay(_http_error(429), 0), 20.0)
        self.assertEqual(check_sources._retry_delay(_http_error(503), 1), 40.0)

    def test_other_errors_keep_short_backoff(self) -> None:
        self.assertEqual(check_sources._retry_delay(_http_error(500), 0), 1.0)
        self.assertEqual(check_sources._retry_delay(OSError("reset"), 2), 4.0)


class HostSpacingTest(unittest.TestCase):
    def test_same_host_requests_are_spaced(self) -> None:
        check_sources._last_request_at.clear()
        clock = [100.0]
        sleeps: list[float] = []

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            clock[0] += seconds

        with (
            mock.patch.object(check_sources.time, "monotonic", lambda: clock[0]),
            mock.patch.object(check_sources.time, "sleep", sleep),
        ):
            check_sources._wait_for_host("bip.ure.gov.pl")
            clock[0] += 1.0
            check_sources._wait_for_host("bip.ure.gov.pl")
            check_sources._wait_for_host("eon.pl")
        self.assertEqual(sleeps, [check_sources.HOST_SPACING_SECONDS - 1.0])


if __name__ == "__main__":
    unittest.main()
