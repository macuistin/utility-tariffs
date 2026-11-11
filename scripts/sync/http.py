"""Polite HTTP for the sync: one honest user agent, a pause after each request, three tries.

A `Fetcher` can also save every response to a folder (`record`) or answer only from one (`replay`),
so a run can be repeated without the network and a test never touches it.
"""
from __future__ import annotations

import hashlib
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "tariff-prices-sync/1.0 (reads public tariff data a few times a week; see repository)"
DELAY_SECONDS = 2
RETRY_AFTER_SECONDS = (5, 20)  # waits before a second and a third try


class Blocked(Exception):
    """A request failed."""


def file_name(url: str) -> str:
    """A readable, unique file name for a URL."""
    tail = re.sub(r"[^A-Za-z0-9.]+", "_", url.split("://", 1)[-1])[:80].strip("_")
    return f"{tail}.{hashlib.sha256(url.encode()).hexdigest()[:12]}"


class Fetcher:
    def __init__(self, *, record: Path | None = None, replay: Path | None = None,
                 delay: float = DELAY_SECONDS, opener=urllib.request.urlopen,
                 sleep=time.sleep) -> None:
        self.record, self.replay, self.delay = record, replay, delay
        self._open, self._sleep = opener, sleep
        self.requests = 0

    def get(self, url: str, headers: dict | None = None) -> bytes:
        """The body at `url`. Raises Blocked on a refusal, or a failure after three tries."""
        if self.replay is not None:
            path = self.replay / file_name(url)
            if not path.exists():
                raise Blocked(f"{url}: not in the saved responses ({path.name})")
            return path.read_bytes()
        body = self._request(url, headers)
        if self.record is not None:
            self.record.mkdir(parents=True, exist_ok=True)
            (self.record / file_name(url)).write_bytes(body)
        return body

    def _request(self, url: str, headers: dict | None) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        waits = iter(RETRY_AFTER_SECONDS)
        while True:
            self.requests += 1
            try:
                with self._open(request, timeout=60) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                wait = next(waits, None) if error.code in (429, 500, 502, 503, 504) else None
                if wait is None:
                    raise Blocked(f"{url}: HTTP {error.code}") from error
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                wait = next(waits, None)
                if wait is None:
                    raise Blocked(f"{url}: {error}") from error
            finally:
                self._sleep(self.delay)
            self._sleep(wait)
