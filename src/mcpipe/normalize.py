"""Stage 3 — turn staged feed rows into typed `raw_offer` records.

`load` dumped every feed line into `stg_feed_row` as raw JSON. This stage reads
those rows back, picks out the fields we care about (per merchant, using the
column map in `feeds.py`), computes a *stable* merchant key, and upserts one
`raw_offer` per key.

The merchant key (`merchant_sku`) is the whole point:

  * Speedway / La Bécanerie / Motoblouz publish a stable product id  -> use it.
  * Maxxess / Moto-Axxe recycle their ids and GTINs on every refresh, which is
    what bloated the v1 catalogue to ~430k rows for ~16k real products. Their
    own product URL (`maxxess.fr/produit/...`) *does* stay put, so we key on a
    hash of that instead.

Freshness: every offer seen in this run gets `last_seen = <run start>` and
`is_live = true`; anything with an older `last_seen` is flipped to
`is_live = false` (it fell out of the feed).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

from .db import connect
from .feeds import FeedSpec

# order matters: matches the COPY column list and the INSERT below
_OFFER_COLS = (
    "merchant_id",
    "merchant_sku",
    "raw_gtin",
    "raw_title",
    "raw_brand",
    "raw_color",
    "raw_size",
    "raw_mpn",
    "raw_item_group",
    "raw_category",
    "deeplink",
    "image_url",
)


@dataclass
class NormalizeResult:
    feed: str
    upserted: int
    retired: int
    seconds: float


def _ci_get(row: dict, names: list[str]) -> str | None:
    """First present, non-empty value among `names`, matched case-insensitively."""
    if not names:
        return None
    lowered: dict[str, object] | None = None
    for n in names:
        v = row.get(n)
        if v is None:
            if lowered is None:
                lowered = {k.lower(): val for k, val in row.items()}
            v = lowered.get(n.lower())
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def _target_url(deeplink: str) -> str | None:
    """The merchant's own product URL, unwrapped from the affiliate redirect."""
    params = parse_qs(urlparse(deeplink).query)
    for key in ("url", "ourl", "redirect"):
        if params.get(key):
            return unquote(params[key][0])
    return None


def _merchant_sku(feed: FeedSpec, row: dict, deeplink: str) -> str | None:
    if feed.gtin_trust == "synthetic":
        target = _target_url(deeplink)
        if not target:
            return None
        canon = target.split("?", 1)[0].rstrip("/").lower()
        return "u:" + hashlib.md5(canon.encode(), usedforsecurity=False).hexdigest()
    return _ci_get(row, feed.columns.get("merchant_ref", []))


def _category(feed: FeedSpec, row: dict) -> str | None:
    if feed.platform == "effinity":
        parts = [
            _ci_get(row, feed.columns.get(k, []))
            for k in ("category", "category_l2", "category_l3")
        ]
        joined = " > ".join(p for p in parts if p)
        return joined or None
    return _ci_get(row, feed.columns.get("category", []))


_CREATE_TEMP = """
CREATE TEMP TABLE _norm (
    merchant_id    smallint,
    merchant_sku   text,
    raw_gtin       text,
    raw_title      text,
    raw_brand      text,
    raw_color      text,
    raw_size       text,
    raw_mpn        text,
    raw_item_group text,
    raw_category   text,
    deeplink       text,
    image_url      text
) ON COMMIT DROP
"""

_UPSERT = f"""
INSERT INTO raw_offer ({", ".join(_OFFER_COLS)}, last_seen, is_live)
SELECT DISTINCT ON (merchant_sku) {", ".join(_OFFER_COLS)}, %s, true
FROM _norm
ORDER BY merchant_sku
ON CONFLICT (merchant_id, merchant_sku) DO UPDATE SET
    raw_gtin       = EXCLUDED.raw_gtin,
    raw_title      = EXCLUDED.raw_title,
    raw_brand      = EXCLUDED.raw_brand,
    raw_color      = EXCLUDED.raw_color,
    raw_size       = EXCLUDED.raw_size,
    raw_mpn        = EXCLUDED.raw_mpn,
    raw_item_group = EXCLUDED.raw_item_group,
    raw_category   = EXCLUDED.raw_category,
    deeplink       = EXCLUDED.deeplink,
    image_url      = EXCLUDED.image_url,
    last_seen      = EXCLUDED.last_seen,
    is_live        = true
"""


def normalize_feed(feed: FeedSpec) -> NormalizeResult:
    t0 = time.time()
    cols = feed.columns
    write = connect()
    read = connect()
    try:
        with write.cursor() as cur:
            cur.execute("SELECT now()")
            run_start = cur.fetchone()[0]
            cur.execute(_CREATE_TEMP)

        n = 0
        with read.cursor(name="stg") as src:
            src.itersize = 5_000
            src.execute(
                "SELECT row FROM stg_feed_row WHERE merchant_id = %s", (feed.merchant_id,)
            )
            copy_sql = f"COPY _norm ({', '.join(_OFFER_COLS)}) FROM STDIN"
            with write.cursor() as cur, cur.copy(copy_sql) as cp:
                for (row,) in src:
                    deeplink = _ci_get(row, cols.get("link", []))
                    title = _ci_get(row, cols.get("title", []))
                    if not deeplink or not title:
                        continue
                    sku = _merchant_sku(feed, row, deeplink)
                    if not sku:
                        continue
                    gtin = _ci_get(row, cols.get("gtin", []))
                    cp.write_row(
                        (
                            feed.merchant_id,
                            sku,
                            gtin if feed.gtin_trust == "trusted" else None,
                            title,
                            _ci_get(row, cols.get("brand", [])),
                            _ci_get(row, cols.get("color", [])),
                            _ci_get(row, cols.get("size", [])),
                            _ci_get(row, cols.get("mpn", [])),
                            _ci_get(row, cols.get("item_group_id", [])),
                            _category(feed, row),
                            deeplink,
                            _ci_get(row, cols.get("image", [])),
                        )
                    )
                    n += 1

        with write.cursor() as cur:
            cur.execute(_UPSERT, (run_start,))
            cur.execute(
                "UPDATE raw_offer SET is_live = false "
                "WHERE merchant_id = %s AND last_seen < %s",
                (feed.merchant_id, run_start),
            )
            retired = cur.rowcount
        write.commit()
        return NormalizeResult(feed.code, n, retired, time.time() - t0)
    except Exception:
        write.rollback()
        raise
    finally:
        read.close()
        write.close()
