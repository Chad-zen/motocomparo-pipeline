"""Stage — decide what is still true, and what each product costs today.

Three things, in this order:

1. **Freshness.** An offer counts as showable only if the feed still listed it
   *and* we heard from that feed recently. `normalize` already handles the first
   half (it flips `is_live` off for anything missing from a run it actually
   completed). This stage handles the second: an offer whose `last_seen` is
   older than the window is not shown, however alive it looked last time.

   That second half is not redundant — it is the guard against *us* being
   broken rather than the merchant. v1's import froze for three days and nobody
   noticed; it was found by spotting stale prices on the site. With a window,
   a frozen pipeline stops showing prices instead of showing old ones.

   The window is 24 hours, set by the site owner: sending a buyer to a price
   that no longer exists is the worst failure a comparison site can have
   (docs/product-decisions.md).

2. **Price history.** One row per offer per day, appended. This is what later
   draws a price curve, and what lets "was it really cheaper last week?" be
   answered rather than guessed. Re-running on the same day overwrites that
   day's row rather than duplicating it.

3. **Each product's headline price** — the cheapest offer that is both fresh and
   in stock. Out-of-stock offers stay visible on the page with their mention
   (nothing is ever removed from the site), but they must never set the price a
   visitor is promised. A product with nothing in stock gets no headline price
   and is marked `stale`, which is a *display* state, not a deletion.

Note on what `in_stock` means per merchant: only La Bécanerie (24% of its
offers) and Speedway (0.7%) ever declare a stockout. Motoblouz, FC-Moto,
Maxxess and Moto-Axxe report everything as available — so for those four the
freshness window is the only real protection against showing an item that is
gone. That is measured, not assumed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .db import connect

# How old an offer's last sighting may be and still be shown. The owner's rule.
FRESHNESS_WINDOW = "24 hours"

# An offer is showable when the feed still lists it AND we heard from that feed
# inside the window. Used identically by every statement below, so the three
# results can never disagree about what "fresh" means.
_FRESH = f"o.is_live AND o.last_seen >= now() - interval '{FRESHNESS_WINDOW}'"

_APPEND_PRICE_HISTORY = f"""
INSERT INTO price_history (raw_offer_id, observed_on, price, in_stock)
SELECT o.id, (now() AT TIME ZONE 'UTC')::date, o.price, o.in_stock
FROM raw_offer o
WHERE o.price IS NOT NULL AND {_FRESH}
ON CONFLICT (raw_offer_id, observed_on) DO UPDATE SET
    price = EXCLUDED.price, in_stock = EXCLUDED.in_stock
"""

# cheapest fresh, in-stock offer. `in_stock IS NOT FALSE` on purpose: a merchant
# that says nothing (NULL) must not be treated as out of stock — see the module
# note above, four of six merchants never declare a stockout at all.
_RECOMPUTE_MIN_PRICE = f"""
UPDATE product p SET min_price = q.cheapest
FROM (
    SELECT o.product_id, min(o.price) AS cheapest
    FROM raw_offer o
    WHERE o.linked_status = 'linked' AND o.product_id IS NOT NULL
      AND o.price IS NOT NULL AND o.in_stock IS NOT FALSE AND {_FRESH}
    GROUP BY o.product_id
) q
WHERE q.product_id = p.id AND p.min_price IS DISTINCT FROM q.cheapest
"""

# everything that no longer has such an offer loses its headline price
_CLEAR_STALE_PRICES = f"""
UPDATE product p SET min_price = NULL
WHERE p.min_price IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM raw_offer o
      WHERE o.product_id = p.id AND o.linked_status = 'linked'
        AND o.price IS NOT NULL AND o.in_stock IS NOT FALSE AND {_FRESH}
  )
"""

# `stale` is a display state — the page stays, it just has nothing to promise.
# `merged` and `published` are owned by other stages and left alone.
_MARK_STALE = f"""
UPDATE product p SET status = 'stale'
WHERE p.status IN ('draft', 'published')
  AND NOT EXISTS (
      SELECT 1 FROM raw_offer o
      WHERE o.product_id = p.id AND o.linked_status = 'linked' AND {_FRESH}
  )
"""

_UNMARK_STALE = f"""
UPDATE product p SET status = 'draft'
WHERE p.status = 'stale'
  AND EXISTS (
      SELECT 1 FROM raw_offer o
      WHERE o.product_id = p.id AND o.linked_status = 'linked' AND {_FRESH}
  )
"""


@dataclass
class FreshnessResult:
    offers_fresh: int
    offers_expired: int
    history_rows: int
    prices_set: int
    prices_cleared: int
    products_stale: int
    products_revived: int
    seconds: float


def run_freshness() -> FreshnessResult:
    """Append today's prices, recompute headline prices, mark what went stale.

    Read-mostly and idempotent: running it twice in a day changes nothing the
    second time. It never deletes a product — a product with no fresh offer is
    marked, not removed (docs/product-decisions.md).
    """
    t0 = time.time()
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT count(*) FILTER (WHERE {_FRESH}), "
                f"count(*) FILTER (WHERE NOT ({_FRESH})) FROM raw_offer o"
            )
            counts = cur.fetchone()
            if counts is None:  # a COUNT always returns a row; be explicit anyway
                raise RuntimeError("freshness: could not read offer counts")
            fresh, expired = counts

            cur.execute(_APPEND_PRICE_HISTORY)
            history_rows = cur.rowcount

            cur.execute(_RECOMPUTE_MIN_PRICE)
            prices_set = cur.rowcount

            cur.execute(_CLEAR_STALE_PRICES)
            prices_cleared = cur.rowcount

            cur.execute(_MARK_STALE)
            products_stale = cur.rowcount

            cur.execute(_UNMARK_STALE)
            products_revived = cur.rowcount

            # La vue `product_stats` porte TOUS les prix que le site affiche en
            # liste — « à partir de … » sur chaque carte, le meilleur prix en
            # haut de fiche, la rangée de l'accueil, la recherche, les compteurs
            # de marques. Sa fonction de rafraîchissement disait elle-même être
            # « appelée à la fin de freshness » ; elle ne l'était par aucune
            # ligne de code. Le site pouvait donc afficher des prix arbitrairement
            # vieux tout en promettant une actualisation quotidienne — le genre
            # d'écart qui ne se voit pas, parce que les chiffres restent
            # plausibles.
            cur.execute("SELECT refresh_product_stats()")

        conn.commit()
        return FreshnessResult(
            fresh, expired, history_rows, prices_set, prices_cleared,
            products_stale, products_revived, time.time() - t0,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
