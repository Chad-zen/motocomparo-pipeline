"""The 5 merchant feeds: where to get each one, its format, and how its columns
map onto our internal fields.

This is deliberately data, not code. Adding or fixing a merchant should be an edit
here, never a change to the parser.

Three feed platforms:

  * Effinity      — ';'-delimited CSV, rich columns (colour, size, mpn, item_group_id).
                    Merchants: Speedway, La Bécanerie, Maxxess, Moto-Axxe.
  * Netaffiliation — '|'-delimited CSV, sparse (no colour, no size, no item_group_id).
                    Merchant: Motoblouz.
  * Webgains      — ','-delimited CSV, Google Shopping schema, the best-filled feed
                    (colour 90%, size 94%, mpn 99%, item_group_id 94%). Needs a
                    bearer token. Merchant: FC-Moto.

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
    # env var holding a bearer token, when the feed endpoint requires one
    auth_token_env: str | None = None

    @property
    def url(self) -> str | None:
        return os.environ.get(f"FEED_{self.code.upper()}_URL") or None

    @property
    def auth_token(self) -> str | None:
        return os.environ.get(self.auth_token_env) if self.auth_token_env else None


_EFFINITY_COLUMNS = {
    "merchant_ref":   ["id"],
    "gtin":           ["gtin"],
    "title":          ["title"],
    "brand":          ["brand"],
    "color":          ["color"],
    "gender":         ["gender"],
    "age_group":      ["age_group"],
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

# Webgains ships a Google-Shopping-style schema (44 columns). `price` is the
# reference price and `sale_price` the promotional one; `normalize` prefers the
# promo when it is lower and in force, because that is what the buyer pays.
# Mapping it was reversed on 2026-09-13: leaving it out quoted the REV'IT
# Stealth 2 at 389.99 when FC-Moto was selling it at 311.99, making the cheapest
# merchant on the page look like the dearest. 45,015 of FC-Moto's offers carry a
# sale price and not one carries an effective-date window.
# merchant_ref falls back mpn -> gtin -> id (the `id` hash's stability is unproven).
_WEBGAINS_COLUMNS = {
    "gtin":           ["gtin"],
    "sale_price":       ["sale_price"],
    "sale_price_window": ["sale_price_effective_date"],
    "title":          ["title"],
    "brand":          ["brand"],
    "color":          ["color"],
    "gender":         ["gender"],
    "age_group":      ["age_group"],
    "size":           ["size"],
    "mpn":            ["mpn"],
    "item_group_id":  ["item_group_id"],
    "merchant_ref":   ["mpn", "gtin", "id"],
    "description":    ["description"],
    "category":       ["product_type", "google_product_category_text"],
    "link":           ["link"],
    "image":          ["image_link"],
    "price":          ["price"],
    "availability":   ["availability"],
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
    "fcmoto": FeedSpec(
        code="fcmoto", merchant_id=6, platform="webgains", delimiter=",",
        gtin_trust="trusted", reliability_rank=2, columns=_WEBGAINS_COLUMNS,
        auth_token_env="FEED_FCMOTO_TOKEN",
    ),
}


def configured_feeds() -> list[FeedSpec]:
    """Feeds that have a URL set in the environment."""
    return [f for f in FEEDS.values() if f.url]
