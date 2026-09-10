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

Header quirks verified against the live feeds (2026-09-10):
  * every header field is wrapped in double quotes — the parser strips them;
  * column matching is case-insensitive (Motoblouz's part-number column is `HAN`);
  * Effinity feeds carry 73 columns, Netaffiliation 20 — we read only the ones below.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FeedSpec:
    code: str                       # 'speedway', 'labecanerie', ...
    merchant_id: int                # stable id, also the PK in the `merchant` table
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
    "merchant_ref":   ["id"],
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
    "image":          ["image_link"],
    "price":          ["price"],
    "currency":       ["currency"],
    "availability":   ["availability"],
    "stock":          ["stock"],
}

_NETAFFILIATION_COLUMNS = {
    "gtin":           ["universal reference"],
    "title":          ["name"],
    "brand":          ["brand"],
    "mpn":            ["HAN"],
    "merchant_ref":   ["internal reference"],
    "category":       ["category"],
    "description":    ["description"],
    "link":           ["product url"],
    "image":          ["image url"],
    "price":          ["price"],
    "crossed_price":  ["crossed price"],
    "availability":   ["availability"],
    "stock":          ["stock"],
}


FEEDS: dict[str, FeedSpec] = {
    "speedway": FeedSpec(
        code="speedway", merchant_id=1, platform="effinity", delimiter=";",
        gtin_trust="trusted", reliability_rank=1, columns=_EFFINITY_COLUMNS,
    ),
    "labecanerie": FeedSpec(
        code="labecanerie", merchant_id=2, platform="effinity", delimiter=";",
        gtin_trust="trusted", reliability_rank=1, columns=_EFFINITY_COLUMNS,
    ),
    "motoblouz": FeedSpec(
        code="motoblouz", merchant_id=3, platform="netaffiliation", delimiter="|",
        gtin_trust="trusted", reliability_rank=2, columns=_NETAFFILIATION_COLUMNS,
    ),
    "maxxess": FeedSpec(
        code="maxxess", merchant_id=4, platform="effinity", delimiter=";",
        gtin_trust="synthetic", reliability_rank=3, columns=_EFFINITY_COLUMNS,
    ),
    "motoaxxe": FeedSpec(
        code="motoaxxe", merchant_id=5, platform="effinity", delimiter=";",
        gtin_trust="synthetic", reliability_rank=3, columns=_EFFINITY_COLUMNS,
    ),
}


def configured_feeds() -> list[FeedSpec]:
    """Feeds that have a URL set in the environment."""
    return [f for f in FEEDS.values() if f.url]
