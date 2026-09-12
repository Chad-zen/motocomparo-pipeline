"""Stage — correct coarse feed categories, per offer, before `match` clusters.

Two corrections live here, both writing `offer_category_override`, which
`match._COMPUTE_OFFER_IDENTITY` reads ahead of `category_map`. Both are scoped
to a CLOSED list of (merchant, feed-category) buckets known to be too coarse —
never a whole merchant, because the title/neighbour signals are only safe where
the feed's own category is a known catch-all.

1. **Coarse apparel buckets** (FC-Moto `tops`): the feed dumps real motorcycle
   jackets under one bucket the classifier reads as `apparel_casual`. When the
   title clearly names a jacket (or trousers, suit, protection…), re-read the
   category from the title.

2. **Coarse helmet buckets** (FC-Moto `helmets`): the feed dumps every helmet
   type under one bucket the classifier forces to `helmet.integral` — jets,
   modulars and cross helmets included, plus a few items that are not
   motorcycle helmets at all. Corrected by a three-step cascade, in this order:

   a. *Not a motorcycle helmet* — the feed's own `google_product_category_text`
      cleanly flags bicycle helmets, ski helmets and goggles. These go to
      `unknown` (25), never to a positive category: 25 is the sentinel
      `match`'s conflict gate deliberately ignores, so it blocks nothing, while
      claiming "accessories" would be a false statement that disagrees with
      every other merchant and quarantines the group.
   b. *Borrow the subtype from a neighbour* — another merchant sharing the same
      validated GTIN is selling the same physical helmet, so its own (specific)
      subtype is direct evidence. Borrowed only when every such neighbour
      agrees. Measured on live data: 7,223 helmets recoverable, 5 ambiguous.
   c. *Fall back to the title* — only when no neighbour can lend, and only on
      an unambiguous single-subtype read.

   Why borrowing outranks the title: a title can name two types at once
   ("casque modulable à mentonnière intégrale"), and the adventure/trail family
   is titled "enduro/cross" by FC-Moto while every other merchant calls it
   integral. Trusting the title there would *contradict* neighbours that agree
   today and cost ~851 working merges. Borrowing can only ever resolve a
   disagreement, never pull two different items together — the GTIN already
   guarantees they are the same article.

Safety, both corrections: an override is written ONLY when the result differs
from the feed's current mapping, so a silent read is a missed fix, never an
invented one. The generic parent `helmet` (1) is never written and never
borrowed, and neither is `unknown` — a non-value would look like agreement.
`match`'s conflict gate stays in force throughout, so a mis-read label cannot
cause a false merge, only a wrong-but-consistent label on the right item.

Sibling coarse buckets elsewhere (Motoblouz "Intercoms", "Habillage &
protection", La Bécanerie "Kit plastique") have the same defect and are left
for a follow-up pass: this run clears part, not all, of the category-only
review queue.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from . import textnorm as tn
from .category import _UNKNOWN_ID, classify
from .db import connect

# --- scope -----------------------------------------------------------------

# buckets corrected by reading the title (rule 1), keyed by merchant code
_COARSE_BUCKETS: dict[str, set[str]] = {
    "fcmoto": {"tops"},
}

# buckets corrected by the helmet cascade (rule 2), keyed by merchant code
_HELMET_BUCKETS: dict[str, set[str]] = {
    "fcmoto": {"helmets"},
}

# the specific helmet subtypes; `helmet` (1, the generic parent) is excluded on
# purpose — writing or borrowing it would disagree with every sibling subtype
_HELMET_SUBTYPE_IDS = frozenset({2, 3, 4, 5})

# Google's own taxonomy, straight from the feed: what is NOT a motorcycle helmet
_NOT_A_MOTO_HELMET = re.compile(
    r"bicycle helmets|ski & snowboard helmets|goggles", re.I
)

# one specific subtype per pattern; two matches in one title = ambiguous = abstain.
# `flip` is deliberately NOT a modular keyword: flip-up means modular in English,
# but in this catalogue "Flip" is a product line ("Acerbis Flip FS-606"), and it
# only ever fired on visors — 27 of them.
_HELMET_TITLE_RULES: list[tuple[re.Pattern, int]] = [
    (re.compile(r"modulable|modular"), 4),
    (re.compile(r"cross"), 5),
    (re.compile(r"\bjet\b|demi ?jet|\bbol\b"), 3),
    (re.compile(r"integral|full ?face"), 2),
]

# Spare parts sold inside the helmet bucket. They name a helmet type only to say
# which helmet they FIT ("Shark RS Jet Visière"), so a subtype read off them is
# always wrong — they are not helmets at all.
_HELMET_ACCESSORY = re.compile(
    r"visiere|visor|ecran|pinlock|mentonniere|coiffe|mousse|bavette|spoiler"
)
# ...but a helmet's own MODEL NAME can contain one of those words: "Nolan N20-2
# Visor Dolce Vita Casque a reaction" is a real jet helmet. So an accessory word
# only wins when the title does not present itself as a helmet — or when it says
# outright that it fits one ("Visiere du casque", "Visor pour Jet Helmet").
_IS_A_HELMET_ITSELF = re.compile(r"\bcasque\b|\bhelmet\b")
_FITS_A_HELMET = re.compile(r"(?:du|de|pour)\s+(?:le\s+)?(?:casque|helmet)"
                            r"|pour\s+\w+\s+helmet")


# --- pure decisions (offline-testable) -------------------------------------


def decide_override(title: str | None, mapped_category_id: int) -> int | None:
    """Rule 1: corrected category for one coarse-bucket offer, or None to leave
    it alone. Overrides only on a confident title read that changes something."""
    new_id = classify(None, title)
    if new_id == _UNKNOWN_ID or new_id == mapped_category_id:
        return None
    return new_id


def helmet_subtype_from_title(title: str | None) -> int | None:
    """The one specific helmet subtype named in a title, or None when none is
    named or two are (e.g. "modulable à mentonnière intégrale")."""
    blob = tn.norm_txt(title)
    if not blob:
        return None
    hits = {cid for pattern, cid in _HELMET_TITLE_RULES if pattern.search(blob)}
    return hits.pop() if len(hits) == 1 else None


def is_helmet_accessory(title: str | None) -> bool:
    """True for a spare part sold in the helmet bucket (a visor, a liner…), as
    opposed to a helmet whose model name merely contains one of those words."""
    blob = tn.norm_txt(title)
    if not blob or not _HELMET_ACCESSORY.search(blob):
        return False
    return not _IS_A_HELMET_ITSELF.search(blob) or bool(_FITS_A_HELMET.search(blob))


def decide_helmet_category(
    title: str | None,
    neighbour_category_ids: list[int] | tuple[int, ...],
    google_category: str | None,
) -> int | None:
    """Rule 2's cascade — not-a-helmet, then borrow, then title. Returns the
    corrected category id, or None to leave the offer as the feed had it."""
    if google_category and _NOT_A_MOTO_HELMET.search(google_category):
        return _UNKNOWN_ID
    # a visor is not a helmet whatever the neighbours call it, so this outranks
    # borrowing too
    if is_helmet_accessory(title):
        return _UNKNOWN_ID

    lendable = {c for c in neighbour_category_ids if c in _HELMET_SUBTYPE_IDS}
    if len(lendable) == 1:
        return lendable.pop()
    if lendable:
        return None  # neighbours disagree with each other — abstain

    return helmet_subtype_from_title(title)


# --- stage -----------------------------------------------------------------


@dataclass
class EnrichResult:
    candidates_scanned: int
    overrides_written: int
    by_target: dict[int, int] = field(default_factory=dict)
    by_rule: dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0


_SELECT_COARSE = """
SELECT o.id, o.raw_title, coalesce(cm.category_id, %s) AS mapped
FROM raw_offer o
JOIN merchant m ON m.id = o.merchant_id
LEFT JOIN category_map cm
    ON cm.merchant_id = o.merchant_id AND cm.raw_path = o.raw_category
WHERE m.code = %s AND o.raw_category = ANY(%s)
"""

# candidates + what their GTIN neighbours at OTHER merchants call themselves.
# Neighbour categories are read the same way `match` will read them
# (override first, then the feed's map), so enrich and match never see two
# different values for the same offer.
_SELECT_HELMETS = """
WITH cand AS (
    SELECT o.id, o.gtin, o.raw_title, o.merchant_sku,
           coalesce(cm.category_id, %(unknown)s) AS mapped
    FROM raw_offer o
    LEFT JOIN category_map cm
        ON cm.merchant_id = o.merchant_id AND cm.raw_path = o.raw_category
    WHERE o.merchant_id = %(mid)s AND o.raw_category = ANY(%(buckets)s)
),
neighbours AS (
    SELECT c.id,
           array_agg(DISTINCT coalesce(ovr.category_id, cm2.category_id, %(unknown)s))
               AS cats
    FROM cand c
    JOIN raw_offer o2 ON o2.gtin = c.gtin AND o2.merchant_id <> %(mid)s
    LEFT JOIN category_map cm2
        ON cm2.merchant_id = o2.merchant_id AND cm2.raw_path = o2.raw_category
    LEFT JOIN offer_category_override ovr ON ovr.raw_offer_id = o2.id
    WHERE c.gtin IS NOT NULL
    GROUP BY c.id
)
SELECT c.id, c.raw_title, c.mapped, c.merchant_sku, coalesce(n.cats, '{}') AS cats
FROM cand c
LEFT JOIN neighbours n ON n.id = c.id
"""

# the feed's own Google taxonomy text, one row per merchant SKU
_SELECT_GOOGLE_CATEGORIES = """
SELECT DISTINCT ON (row->>'mpn')
       row->>'mpn' AS sku, row->>'google_product_category_text' AS google_cat
FROM stg_feed_row
WHERE merchant_id = %s AND row->>'product_type' = ANY(%s)
"""


def enrich_categories() -> EnrichResult:
    """Rebuild `offer_category_override` from the closed bucket lists.

    Idempotent: every rule is recomputed and the table is replaced in one go,
    so re-running is safe and always reflects the current rules. Must run
    BEFORE `match`, which reads the overrides when it recomputes identities.
    """
    t0 = time.time()
    conn = connect()
    scanned = 0
    overrides: list[tuple[int, int]] = []
    by_rule: dict[str, int] = {"title_reclass": 0, "helmet_borrowed": 0,
                               "helmet_title": 0, "not_a_helmet": 0}
    try:
        with conn.cursor() as cur:
            # --- rule 1: coarse apparel buckets, read from the title ---
            for merchant_code, buckets in _COARSE_BUCKETS.items():
                cur.execute(_SELECT_COARSE, (_UNKNOWN_ID, merchant_code, list(buckets)))
                for offer_id, title, mapped in cur.fetchall():
                    scanned += 1
                    new_id = decide_override(title, mapped)
                    if new_id is not None:
                        overrides.append((offer_id, new_id))
                        by_rule["title_reclass"] += 1

            # --- rule 2: helmet buckets, borrow-then-title cascade ---
            for merchant_code, buckets in _HELMET_BUCKETS.items():
                cur.execute("SELECT id FROM merchant WHERE code = %s", (merchant_code,))
                row = cur.fetchone()
                if row is None:
                    continue
                merchant_id = row[0]
                bucket_list = list(buckets)

                cur.execute(_SELECT_GOOGLE_CATEGORIES, (merchant_id, bucket_list))
                google_by_sku = {sku: cat for sku, cat in cur.fetchall()}

                cur.execute(
                    _SELECT_HELMETS,
                    {"unknown": _UNKNOWN_ID, "mid": merchant_id, "buckets": bucket_list},
                )
                for offer_id, title, mapped, sku, cats in cur.fetchall():
                    scanned += 1
                    google_cat = google_by_sku.get(sku)
                    new_id = decide_helmet_category(title, cats or [], google_cat)
                    if new_id is None or new_id == mapped:
                        continue
                    overrides.append((offer_id, new_id))
                    if new_id == _UNKNOWN_ID:
                        by_rule["not_a_helmet"] += 1
                    elif {c for c in (cats or []) if c in _HELMET_SUBTYPE_IDS}:
                        by_rule["helmet_borrowed"] += 1
                    else:
                        by_rule["helmet_title"] += 1

            # --- replace the whole derived table in one go ---
            cur.execute("TRUNCATE offer_category_override")
            if overrides:
                cur.executemany(
                    "INSERT INTO offer_category_override "
                    "(raw_offer_id, category_id, source, confidence) "
                    "VALUES (%s, %s, 'enrich', 0.80)",
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
    return EnrichResult(scanned, len(overrides), by_target, by_rule, time.time() - t0)
