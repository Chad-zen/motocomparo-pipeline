"""Stage 1 — download each configured merchant feed to disk.

Streaming, so a 375 MB file never lands in memory. Writes to a `.part` file and
renames on success, so a killed download never leaves a truncated feed in place.

Not implemented yet — see docs/roadmap.md phase 1.
"""

from __future__ import annotations

from pathlib import Path

from .feeds import FeedSpec


def fetch_feed(feed: FeedSpec, dest_dir: Path) -> Path:
    raise NotImplementedError("phase 1")
