"""The 5 merchant feeds: where to get each one, its format, and how its columns
map onto our internal fields.

This is deliberately data, not code. Adding or fixing a merchant should be an edit
here, never a change to the parser.

Two feed platforms:

  * Effinity      — ';'-delimited CSV, rich columns (colour, size, mpn, item_group_id).
                    Merchants: Speedway, La Bécanerie, Maxxess, Moto-Axxe.
  * Netaffiliation — '|'-delimited CSV, sparse (no colour, no size, no item_group_id).
                    Merchant: Motoblouz.

GTIN trust: Speedway / La Bécanerie / Motoblouz emit real, stable barcodes — safe to
join on. Maxxess / Moto-Axxe emit synthetic sequential ids that change every refresh —
`gtin_trust="synthetic"`, never used as a key (see docs/architecture.md).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FeedSpec:
    code: str                       # 'speedway', 'labecanerie', ...
    platform: str                   # 'effinity' | 'netaffiliation'
    delimiter: str
    gtin_trust: str                 # 'trusted' | 'synthetic'
    reliability_rank: int           # 1 = most trusted, used to break attribute ties
    # internal field  ->  list of acceptable column names in the feed header
    columns: dict[str, list[str]] = field(default_factory=dict)

    @property
    def url(self) -> str | None:
        return os.environ.get(f"FEED_{self.code.upper()}_URL") or None


_EFFINITY_COLUMNS = {
    "gtin":           ["gtin"],
    "title":          ["title"],
    "brand":          ["brand"],
    "color":          ["color"],
    "gender":         ["gender"],
    "size":           ["size"],
    "mpn":            ["mpn"],
    "item_group_id":  ["item_group_id"],
    "description":    ["description"],
    "category":       ["category"],
    "category_l2":    ["category_level2"],
    "category_l3":    ["category_level3"],
    "link":           ["link"],
    "image":          ["image_link", "image"],
    "price":          ["price"],
    "availability":   ["availability"],
}

_NETAFFILIATION_COLUMNS = {
    "gtin":         ["universal reference", "reference"],
    "title":        ["name"],
    "brand":        ["brand", "manufacturer"],
    "mpn":          ["han"],
    "category":     ["category"],
    "description":  ["description"],
    "link":         ["product url", "url"],
    "image":        ["image url", "image"],
    "price":        ["price"],
    "availability": ["availability", "in stock"],
}


FEEDS: dict[str, FeedSpec] = {
    "speedway": FeedSpec(
        code="speedway", platform="effinity", delimiter=";",
        gtin_trust="trusted", reliability_rank=1, columns=_EFFINITY_COLUMNS,
    ),
    "labecanerie": FeedSpec(
        code="labecanerie", platform="effinity", delimiter=";",
        gtin_trust="trusted", reliability_rank=1, columns=_EFFINITY_COLUMNS,
    ),
    "motoblouz": FeedSpec(
        code="motoblouz", platform="netaffiliation", delimiter="|",
        gtin_trust="trusted", reliability_rank=2, columns=_NETAFFILIATION_COLUMNS,
    ),
    "maxxess": FeedSpec(
        code="maxxess", platform="effinity", delimiter=";",
        gtin_trust="synthetic", reliability_rank=3, columns=_EFFINITY_COLUMNS,
    ),
    "motoaxxe": FeedSpec(
        code="motoaxxe", platform="effinity", delimiter=";",
        gtin_trust="synthetic", reliability_rank=3, columns=_EFFINITY_COLUMNS,
    ),
}


def configured_feeds() -> list[FeedSpec]:
    """Feeds that have a URL set in the environment."""
    return [f for f in FEEDS.values() if f.url]
