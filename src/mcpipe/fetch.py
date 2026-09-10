"""Stage 1 — download each configured merchant feed to disk.

Streamed: bytes are written straight to a file as they arrive, so a 375 MB feed
never sits in memory. The download goes to `<code>.csv.part` and is renamed to
`<code>.csv` only once it completes — a killed download never leaves a truncated
file that a later stage would try to parse.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from .feeds import FeedSpec

# feeds are big; be patient on the body, quick to give up on a dead connection
_TIMEOUT = httpx.Timeout(connect=15.0, read=120.0, write=30.0, pool=15.0)
_MIN_BYTES = 1_000  # anything smaller than this is an error page, not a feed


@dataclass
class FetchResult:
    feed: str
    path: Path
    bytes: int
    seconds: float
    from_cache: bool = False


def fetch_feed(
    feed: FeedSpec,
    dest_dir: Path,
    *,
    max_age_seconds: float | None = 3 * 3600,
    on_progress=None,
) -> FetchResult:
    """Download one feed. Reuses an existing file younger than `max_age_seconds`
    (set to None to always re-download)."""
    if feed.url is None:
        raise ValueError(f"feed {feed.code!r} has no URL configured")

    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / f"{feed.code}.csv"
    part = dest_dir / f"{feed.code}.csv.part"

    if (
        max_age_seconds is not None
        and final.exists()
        and final.stat().st_size >= _MIN_BYTES
        and (time.time() - final.stat().st_mtime) < max_age_seconds
    ):
        return FetchResult(feed.code, final, final.stat().st_size, 0.0, from_cache=True)

    t0 = time.time()
    written = 0
    part.unlink(missing_ok=True)
    with httpx.stream("GET", feed.url, timeout=_TIMEOUT, follow_redirects=True) as r:
        r.raise_for_status()
        with part.open("wb") as fh:
            for chunk in r.iter_bytes(chunk_size=1 << 20):  # 1 MiB
                fh.write(chunk)
                written += len(chunk)
                if on_progress is not None:
                    on_progress(feed.code, written)

    if written < _MIN_BYTES:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"{feed.code}: got only {written} bytes — looks like an error page")

    os.replace(part, final)  # atomic on the same filesystem
    return FetchResult(feed.code, final, written, time.time() - t0)
