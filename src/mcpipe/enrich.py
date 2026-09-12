"""Stage — correct coarse feed categories from the product title.

The narrow, high-value fix this implements: FC-Moto ships real motorcycle
jackets under a single coarse feed category `tops`, which the keyword
classifier maps to `apparel_casual`. When an offer's title clearly names a
jacket (or trousers, gloves, …), re-read its category FROM THE TITLE and store
a per-offer row in `offer_category_override`. `match._COMPUTE_OFFER_IDENTITY`
reads that override ahead of `category_map`, so the corrected category flows
into every merge decision on the next `match` run — clearing review-queue
groups that only disagreed on category.

Scope is a CLOSED list of known-coarse (merchant, feed-category) buckets,
seeded with FC-Moto `tops` only. Sibling coarse buckets (`pants`, `suits`,
`protectors`) share the same defect and are left for a follow-up pass, so this
run clears PART, not all, of the category-only review queue — on purpose.

Safety. An override is written ONLY when the title yields a confident,
non-`unknown` category that DIFFERS from the feed's current mapping. A title
with no strong keyword is left untouched (a missed fix, never a wrong one).
The category conflict gate in `match` stays in force regardless, so a mis-read
label can never cause a false merge — at worst a wrong-but-consistent label on
the right physical item. (Checked against shared barcodes: 98.5% of the
reclassified `tops` jackets are confirmed `jacket` by an independent merchant.)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .category import _UNKNOWN_ID, classify
from .db import connect

# Closed list of feed buckets known to be too coarse, keyed by merchant CODE.
# Seed: FC-Moto `tops` only. Add siblings here (a later pass), never widen to a
# whole merchant — the title is only a safe override where the feed category is
# a known catch-all.
_COARSE_BUCKETS: dict[str, set[str]] = {
    "fcmoto": {"tops"},
}


def decide_override(title: str | None, mapped_category_id: int) -> int | None:
    """The per-offer decision, kept pure so it can be tested offline.

    Returns the corrected category id, or None to leave the offer as-is.
    Overrides only on a confident title read that changes the category.
    """
    new_id = classify(None, title)
    if new_id == _UNKNOWN_ID:
        return None
    if new_id == mapped_category_id:
        return None
    return new_id


@dataclass
class EnrichResult:
    candidates_scanned: int
    overrides_written: int
    by_target: dict[int, int] = field(default_factory=dict)
    seconds: float = 0.0


_SELECT_CANDIDATES = """
SELECT o.id, o.raw_title, coalesce(cm.category_id, %s) AS mapped
FROM raw_offer o
JOIN merchant m ON m.id = o.merchant_id
LEFT JOIN category_map cm
    ON cm.merchant_id = o.merchant_id AND cm.raw_path = o.raw_category
WHERE m.code = %s AND o.raw_category = ANY(%s)
"""


def enrich_categories() -> EnrichResult:
    """Rebuild `offer_category_override` from the closed coarse-bucket list.

    Idempotent: truncates then repopulates, so re-running is safe and reflects
    the current title-classification rules. Must run BEFORE `match`.
    """
    t0 = time.time()
    conn = connect()
    scanned = 0
    overrides: list[tuple[int, int]] = []
    try:
        with conn.cursor() as cur:
            for merchant_code, buckets in _COARSE_BUCKETS.items():
                cur.execute(
                    _SELECT_CANDIDATES,
                    (_UNKNOWN_ID, merchant_code, list(buckets)),
                )
                for offer_id, title, mapped in cur.fetchall():
                    scanned += 1
                    new_id = decide_override(title, mapped)
                    if new_id is not None:
                        overrides.append((offer_id, new_id))

            cur.execute("TRUNCATE offer_category_override")
            if overrides:
                cur.executemany(
                    "INSERT INTO offer_category_override "
                    "(raw_offer_id, category_id, source, confidence) "
                    "VALUES (%s, %s, 'title_reclass', 0.80)",
                    overrides,
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    by_target: dict[int, int] = {}
    for _oid, cid in overrides:
        by_target[cid] = by_target.get(cid, 0) + 1
    return EnrichResult(scanned, len(overrides), by_target, time.time() - t0)
