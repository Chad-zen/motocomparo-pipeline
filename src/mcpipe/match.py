"""Stage — cluster `raw_offer` into `product` rows.

v1 scope, per the reviewed plan: GTIN + `item_group_id` only. Maxxess /
Moto-Axxe (no reliable GTIN, no `item_group_id`) and any offer with a weak
signature stay `unresolved`, waiting for a fuzzy stage that isn't built yet.

Design (v2 of this module — the first version was too strict, see below):

A *unit* is either a validated GTIN (spanning merchants — the same real item)
or one merchant's `(item_group_id, colour)` pair. A unit's `identity_hash` is
built from two kinds of fields, on purpose treated differently:
- gated fields (brand, category, colour, year, genre/age, pack) — the
  conflict check below already guarantees at most one distinct non-null
  value per field across a non-conflicting unit's members, so each one is
  taken independently, straight from whichever member has it.
- wording fields (model anchor, model tokens) — NOT gated (see why below),
  so these still come from one best-`model_strength` member, same as before.

Units that reduce to the same hash are the same product, regardless of which
unit or merchant found it first — every member offer of the unit links to
that product, not just the one that contributed its wording fields.

Why per-*unit*, not per-*offer*: the first version computed one identity_hash
per raw offer and required every offer sharing a GTIN to match exactly. In
this catalogue, the same real product often gets a longer, differently-worded
title from one merchant than another (extra colour/fit words, a longer
category tail), so `model_tokens` genuinely differ even though it is the same
item — that alone caused 86% of "GTIN conflicts" in testing. Picking one
representative per unit for the identity computation, then trusting the GTIN
(or item_group) to carry every other member along, removes that noise. GTIN
conflicts now only fire on the attributes that are meant to gate a merge —
brand, category, colour, genre/age, pack, year — never on how a title
happened to be worded. (`brand_code` was missing from this gate until a
systematic invariant review caught it: two offers could in principle share a
GTIN — a data error, not a real barcode collision — with different brands
and merge silently. Added alongside `verify.py`, see below.)

`category_id` and `identity_hash` on `offer_signature` are still populated
for every offer (informational / for a future fuzzy stage) but are no longer
what decides a merge.

KNOWN OPEN BUG, not yet fixed (found by an audit agent, reverted after a bad
first attempt — kept here so it isn't silently retried the same way): a GTIN
unit with no `model_core_ref` and only generic tokens (e.g. "Ermax Bulle
Haute" naming a product LINE, not one specific fitment) can share its exact
identity with hundreds of unrelated GTINs — auto parts like screens or brake
lines that are specific to one motorcycle model but never say which one in
the title. Live example: 1,314 different validated GTINs, almost certainly
1,314 different real fitments, merged onto one "Ermax Bulle Haute" product;
~35,000 offers affected across several such product lines from one merchant
with generic titles and no `item_group_id`.

First fix attempt: when `model_core_ref` is NULL, key identity on the GTIN
itself instead of the shared generic wording. Reverted — it fired on far
more than the fitment-parts case (73% of products have no `model_core_ref`
at all, most of them completely ordinary items with a short, plain title,
not fitment parts). It took products from 236,766 to 458,887, and the new
ones averaged 1.15 offers each — it had stopped nearly all cross-GTIN
merging for anything without a strong title, defeating the point of a
comparison site for most of the catalogue to fix a bug affecting ~35k
offers. `model_core_ref` alone can't distinguish "generic title, but still
the same real item in different sizes" from "generic title shared by
hundreds of genuinely different items" — both look identical by that one
field. The discriminator that DOES separate them, measured since (full
figures in docs/roadmap.md, "The one bug still open"): distinct GTINs *per
distinct size*. A real product runs ~1-2 GTINs per size; the mega-merges run
233 per size, all inside a single "one size" bucket. Still not implemented
on purpose — that ratio is confounded today by Motoblouz having no size
column at all, so ordinary apparel whose sizes never parsed (12 GTINs, one
"TU" size) looks identical to a fitment part at moderate ratios. Fix size
extraction first, then this becomes a clean check, rather than a blanket
per-field rule. Whatever the threshold, the action is `match_review_queue`,
never a silent split.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from psycopg.types.json import Jsonb

from .db import connect


@dataclass
class MatchResult:
    products_created: int
    variants_created: int
    offers_linked_gtin: int
    offers_linked_item_group: int
    gtin_conflicts: int
    seconds: float


# informational identity per offer: category + a hash of the fields that
# would define its product IF it were the sole source of truth. Not used
# below to gate a merge (see module docstring) — kept for `enrich`/a future
# fuzzy stage, and it's cheap (server-side, one pass).
_COMPUTE_OFFER_IDENTITY = """
UPDATE offer_signature s SET
    category_id = coalesce(ovr.category_id, cm.category_id, 25),
    identity_hash = md5(
        coalesce(s.brand_code, '') || '|' ||
        coalesce(s.primary_colour, '') || '|' ||
        coalesce(s.model_year::text, '') || '|' ||
        coalesce(s.genre_age, '') || '|' ||
        s.is_pack::int::text || '|' ||
        coalesce(s.model_core_ref, '') || ':' || coalesce(array_to_string(s.model_tokens, '-'), '')
    )
FROM raw_offer o
LEFT JOIN category_map cm ON cm.merchant_id = o.merchant_id AND cm.raw_path = o.raw_category
-- per-offer category correction from `enrich` (title reclass of coarse feed
-- buckets), read ahead of the feed's own category — see enrich.py
LEFT JOIN offer_category_override ovr ON ovr.raw_offer_id = o.id
WHERE o.id = s.raw_offer_id
"""

# the fields that actually gate a merge: pick the best-signal offer per GTIN
# as the representative, flag the GTIN as conflicting only when members
# genuinely disagree on colour / genre-age / pack / year (never on wording)
_BUILD_GTIN_UNITS = """
CREATE TEMP TABLE _gtin_unit ON COMMIT DROP AS
WITH members AS (
    SELECT o.id AS raw_offer_id, o.gtin, o.merchant_id,
           s.brand_code, s.primary_colour, s.model_year, s.genre_age, s.is_pack,
           s.model_core_ref, s.model_tokens, s.model_strength, s.category_id
    FROM raw_offer o
    JOIN offer_signature s ON s.raw_offer_id = o.id
    WHERE o.gtin IS NOT NULL
      AND o.linked_status = 'unresolved'
      AND NOT EXISTS (
          SELECT 1 FROM match_override mo
          WHERE mo.scope = 'gtin' AND mo.is_split AND mo.key_value = o.gtin
            AND (mo.merchant_id IS NULL OR mo.merchant_id = o.merchant_id)
      )
),
conflicts AS (
    -- genre_age is '{gender}-{age}' (textnorm.genre_age): gender is 'F'/'H'/
    -- 'U', where 'U' genuinely means "no evidence either way" (excluded from
    -- the count below, same as every other missing-signal case). Age is
    -- 'A'/'E' — but 'A' is ALSO textnorm's DEFAULT when nothing said
    -- otherwise, not proof of "confirmed adult", so it can't be excluded the
    -- same way. Given a false adult/child merge is exactly the kind of
    -- mistake this project treats as unacceptable (favour quarantine over a
    -- wrong merge), age gates on ANY A/E disagreement, no exclusion — found
    -- live: `^U-` was excluding 'U-E' (unisex-*child*) along with 'U-A',
    -- letting a child item merge into an adult product (420 real products,
    -- e.g. an adult visor merged with its own "ENFANT" edition).
    --
    -- category_id excludes 25 (`unknown` — the classifier's catch-all, not a
    -- real disagreement) from the count, same idea as every other sentinel
    -- exclusion here — found live: one offer landing in "unknown" was
    -- blocking an otherwise-clean merge for no reason (5,005 groups).
    SELECT gtin
    FROM members
    GROUP BY gtin
    HAVING count(DISTINCT primary_colour) FILTER (WHERE primary_colour IS NOT NULL) > 1
        OR count(DISTINCT left(genre_age, 1)) FILTER (WHERE left(genre_age, 1) != 'U') > 1
        OR count(DISTINCT right(genre_age, 1)) > 1
        OR count(DISTINCT is_pack) > 1
        OR count(DISTINCT model_year) FILTER (WHERE model_year IS NOT NULL) > 1
        OR count(DISTINCT category_id) FILTER (WHERE category_id != 25) > 1
        OR count(DISTINCT brand_code) FILTER (WHERE brand_code IS NOT NULL) > 1
),
-- The gated fields (colour/genre/year/pack/category/brand) are NOT taken
-- from one "representative" row — the `conflicts` gate above already
-- guarantees at most one distinct non-null value per field across the whole
-- (non-conflicting) group, so picking that one value independently per field
-- is always safe and never discards a real signal. Only `model_core_ref`/
-- `model_tokens` still need ONE best-parsed row (by model_strength): those
-- are exactly the free-text fields the gate deliberately does NOT check,
-- because merchants word the same title differently (see module docstring)
-- — aggregating them the same way would reintroduce that noise.
--
-- A first attempt here still picked one row for every field, just with a
-- reordered tiebreak (colour, then genre, then year, then strength) — that
-- only moved the bug: whichever field came LAST in that order could still
-- lose to a member that had nothing to say about it. Found live by
-- `verify.py`: two validated GTINs for the same "Leatt Velocity 6.5"
-- goggles — a 2023 edition and a 2026 edition — collapsed onto one product
-- because both representatives were re-picked for their genre signal,
-- discarding the year each one actually had. Aggregating every gated field
-- independently removes the ordering problem entirely.
gated AS (
    SELECT
        m.gtin,
        (array_agg(m.brand_code) FILTER (WHERE m.brand_code IS NOT NULL))[1]
            AS brand_code,
        (array_agg(m.primary_colour) FILTER (WHERE m.primary_colour IS NOT NULL))[1]
            AS primary_colour,
        (array_agg(m.model_year) FILTER (WHERE m.model_year IS NOT NULL))[1]
            AS model_year,
        -- rebuild from the two halves separately (see `conflicts` above) —
        -- collapsing straight to a single genre_age pick let a real 'U-E'
        -- silently become 'U-A' whenever no member had gender info either.
        coalesce(
            (array_agg(left(m.genre_age, 1)) FILTER (WHERE left(m.genre_age, 1) != 'U'))[1], 'U'
        ) || '-' ||
        (array_agg(right(m.genre_age, 1)))[1] AS genre_age,
        bool_or(m.is_pack) AS is_pack,
        coalesce((array_agg(m.category_id) FILTER (WHERE m.category_id != 25))[1], 25)
            AS category_id
    FROM members m
    GROUP BY m.gtin
),
-- `model_tokens` is itself an array column — array_agg()-ing it produces a
-- 2-D array that a plain `[1]` subscript can't safely pull one row out of,
-- so its (and model_core_ref's) best-row pick stays a DISTINCT ON, same
-- mechanism as before, just kept separate from the gated fields above
-- instead of one row deciding every field.
wording AS (
    SELECT DISTINCT ON (m.gtin) m.gtin, m.model_core_ref, m.model_tokens
    FROM members m
    ORDER BY m.gtin,
             CASE m.model_strength
                 WHEN 'strong' THEN 0 WHEN 'medium' THEN 1 WHEN 'weak' THEN 2 ELSE 3
             END,
             m.raw_offer_id
),
representative AS (
    SELECT g.gtin, g.brand_code, g.primary_colour, g.model_year, g.genre_age,
           g.is_pack, w.model_core_ref, w.model_tokens, g.category_id
    FROM gated g JOIN wording w ON w.gtin = g.gtin
)
SELECT r.*, (c.gtin IS NOT NULL) AS conflict,
       md5(
           coalesce(r.brand_code, '') || '|' || r.category_id::text || '|' ||
           coalesce(r.primary_colour, '') || '|' ||
           coalesce(r.model_year::text, '') || '|' || coalesce(r.genre_age, '') || '|' ||
           r.is_pack::int::text || '|' ||
           coalesce(r.model_core_ref, '') || ':' ||
           coalesce(array_to_string(r.model_tokens, '-'), '')
       ) AS identity_hash
FROM representative r
LEFT JOIN conflicts c ON c.gtin = r.gtin
"""

_FLAG_GTIN_CONFLICTS = """
SELECT gu.gtin, array_agg(o.id ORDER BY o.id),
       jsonb_agg(jsonb_build_object(
           'raw_offer_id', o.id, 'merchant_id', o.merchant_id,
           'colour', s.primary_colour, 'genre_age', s.genre_age,
           'is_pack', s.is_pack, 'model_year', s.model_year,
           'brand_code', s.brand_code, 'category_id', s.category_id,
           'title', left(o.raw_title, 120)
       ) ORDER BY o.id)
FROM _gtin_unit gu
JOIN raw_offer o ON o.gtin = gu.gtin
JOIN offer_signature s ON s.raw_offer_id = o.id
WHERE gu.conflict
GROUP BY gu.gtin
"""

_CREATE_PRODUCTS_FROM_GTIN = """
WITH representative AS (
    SELECT DISTINCT ON (identity_hash)
        identity_hash, category_id, brand_code, primary_colour, model_year,
        genre_age, model_core_ref, model_tokens
    FROM _gtin_unit
    WHERE NOT conflict
    ORDER BY identity_hash
)
INSERT INTO product
    (brand_code, category_id, model_core_ref, model_display, colour_code,
     model_year, genre_age, identity_hash, slug)
SELECT
    coalesce(brand_code, 'unknown'), category_id, model_core_ref,
    initcap(coalesce(model_core_ref,
        nullif(array_to_string(model_tokens, ' '), ''), brand_code, 'unknown')),
    coalesce(primary_colour, 'unknown'),
    model_year,
    coalesce(genre_age, 'U-A'),
    identity_hash,
    regexp_replace(
        left(
            regexp_replace(
                lower(unaccent(
                    coalesce(brand_code, 'unknown') || '-' ||
                    coalesce(model_core_ref, nullif(array_to_string(model_tokens, '-'), ''), 'x') ||
                    '-' || coalesce(primary_colour, 'na')
                )),
                '[^a-z0-9]+', '-', 'g'
            ),
            80
        ),
        '-+$', ''
    ) || '-' || left(identity_hash, 8)
FROM representative
ON CONFLICT (identity_hash) DO NOTHING
"""

_LINK_GTIN_OFFERS = """
UPDATE raw_offer o SET
    product_id = p.id, linked_status = 'linked',
    link_method = 'gtin', link_confidence = 1.00
FROM _gtin_unit gu
JOIN product p ON p.identity_hash = gu.identity_hash
WHERE o.gtin = gu.gtin AND NOT gu.conflict AND o.linked_status = 'unresolved'
  AND NOT EXISTS (
      SELECT 1 FROM match_override mo
      WHERE mo.scope = 'gtin' AND mo.is_split AND mo.key_value = o.gtin
        AND (mo.merchant_id IS NULL OR mo.merchant_id = o.merchant_id)
  )
"""

# item_group_id (labecanerie, fcmoto): for offers a GTIN pass didn't claim,
# unit = one merchant's (item_group_id, identity_hash) — split on the FULL
# hash, not a hand-picked subset of fields. An earlier version split only on
# (colour, category) and missed genre_age/is_pack/model_year, which silently
# merged a men's and a women's item sharing one item_group_id. Computing
# identity_hash per MEMBER first and grouping on it means every field that
# matters for a merge is respected by construction — the split key can't
# drift out of sync with the hash again, because they're the same expression.
_BUILD_ITEM_GROUP_UNITS = """
CREATE TEMP TABLE _ig_unit ON COMMIT DROP AS
WITH members AS (
    SELECT o.id AS raw_offer_id, o.merchant_id, o.raw_item_group,
           s.brand_code, s.primary_colour, s.model_year, s.genre_age, s.is_pack,
           s.model_core_ref, s.model_tokens, s.model_strength, s.category_id,
           md5(
               coalesce(s.brand_code, '') || '|' || s.category_id::text || '|' ||
               coalesce(s.primary_colour, '') || '|' ||
               coalesce(s.model_year::text, '') || '|' || coalesce(s.genre_age, '') || '|' ||
               s.is_pack::int::text || '|' ||
               coalesce(s.model_core_ref, '') || ':' ||
               coalesce(array_to_string(s.model_tokens, '-'), '')
           ) AS identity_hash
    FROM raw_offer o
    JOIN offer_signature s ON s.raw_offer_id = o.id
    WHERE o.linked_status = 'unresolved'
      AND o.raw_item_group IS NOT NULL
      AND s.model_strength IN ('strong', 'medium')
)
SELECT DISTINCT ON (merchant_id, raw_item_group, identity_hash)
    merchant_id, raw_item_group, identity_hash,
    brand_code, primary_colour, model_year, genre_age, is_pack,
    model_core_ref, model_tokens, category_id
FROM members
ORDER BY merchant_id, raw_item_group, identity_hash,
         CASE model_strength WHEN 'strong' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
         raw_offer_id
"""

_CREATE_PRODUCTS_FROM_ITEM_GROUP = """
WITH representative AS (
    SELECT DISTINCT ON (identity_hash)
        identity_hash, category_id, brand_code, primary_colour, model_year,
        genre_age, model_core_ref, model_tokens
    FROM _ig_unit
    ORDER BY identity_hash
)
INSERT INTO product
    (brand_code, category_id, model_core_ref, model_display, colour_code,
     model_year, genre_age, identity_hash, slug)
SELECT
    coalesce(brand_code, 'unknown'), category_id, model_core_ref,
    initcap(coalesce(model_core_ref,
        nullif(array_to_string(model_tokens, ' '), ''), brand_code, 'unknown')),
    coalesce(primary_colour, 'unknown'),
    model_year,
    coalesce(genre_age, 'U-A'),
    identity_hash,
    regexp_replace(
        left(
            regexp_replace(
                lower(unaccent(
                    coalesce(brand_code, 'unknown') || '-' ||
                    coalesce(model_core_ref, nullif(array_to_string(model_tokens, '-'), ''), 'x') ||
                    '-' || coalesce(primary_colour, 'na')
                )),
                '[^a-z0-9]+', '-', 'g'
            ),
            80
        ),
        '-+$', ''
    ) || '-' || left(identity_hash, 8)
FROM representative
ON CONFLICT (identity_hash) DO NOTHING
"""

_LINK_ITEM_GROUP_OFFERS = """
UPDATE raw_offer o SET
    product_id = p.id, linked_status = 'linked',
    link_method = 'item_group', link_confidence = 0.75
FROM offer_signature s, _ig_unit iu, product p
WHERE s.raw_offer_id = o.id
  AND o.merchant_id = iu.merchant_id
  AND o.raw_item_group = iu.raw_item_group
  AND o.linked_status = 'unresolved'
  AND md5(
          coalesce(s.brand_code, '') || '|' || s.category_id::text || '|' ||
          coalesce(s.primary_colour, '') || '|' ||
          coalesce(s.model_year::text, '') || '|' || coalesce(s.genre_age, '') || '|' ||
          s.is_pack::int::text || '|' ||
          coalesce(s.model_core_ref, '') || ':' ||
          coalesce(array_to_string(s.model_tokens, '-'), '')
      ) = iu.identity_hash
  AND p.identity_hash = iu.identity_hash
"""

# What a merchant actually said comes first; a size borrowed from another
# merchant on the same barcode only fills a blank. The reverse order — which
# this line had until 2026-09-13 — meant a borrowed value would keep masking a
# real one for ever, silently, the day the merchant started sending it.
# `TU` is the last resort and means "could not be read", not "one size".
_DECLARED_SIZE = "coalesce(nullif(s.size_code, ''), ovr.size_code, 'TU')"

# One size, one variant. Merchants write the same size several ways: FC-Moto
# ships "M5758" and "XS (55/56)" — a letter plus a head circumference in
# centimetres — where everyone else writes "M"; some glove feeds write "T8" for
# what others call "8". These are notations, not different sizes, and leaving
# them apart put "M · M5758 · L · L59" on one page and broke the size filter.
#
# Deliberately narrow: only a letter size followed by digits, and only a bare
# "T" + digits. A composite the feed sent as one value ("S/M", "US-28") is left
# alone — collapsing it to its first letter would merge two real sizes, which
# costs far more than an ugly label. Letter-to-number equivalence (glove 8 = M,
# jacket EU50 = M) is a per-category referential and is NOT done here.
#
# Measured before applying: 16,429 variants rewritten, 5,767 folding onto a
# size the product already had.
_CANONICAL_SIZE = rf"""regexp_replace(
    regexp_replace(
        upper({_DECLARED_SIZE}),
        '^(XXS|XXL|[2-6]XL|XS|XL|S|M|L)[ ]?[0-9][0-9/ ]*$', '\1'),
    '^T([0-9]{{1,2}})$', '\1')"""

# Categories where a size is a real attribute of the article: helmets, garments,
# protections, casual wear — plus `accessories` (24) and `unknown` (25), kept on
# this side because both hold genuine apparel, and dropping a real size costs
# more than keeping a doubtful one.
_SIZED_CATEGORIES = "(1,2,3,4,5,6,7,8,9,10,11,23,24,25)"

# Everywhere else a size can only have been guessed out of a title or a
# reference, and the guess is wrong often enough to be worth nothing. Measured
# 2026-09-13: saddles carry a size on 81% of their offers and **not one** was
# declared by a feed; engine parts 7,560 sizes for zero declared; suspension
# 2,292 for 6. The mechanism is visible in the data — a Castrol 10W-50 filed as
# "size EU50", with two bottle sizes (16 EUR and 60 EUR) on one page.
#
# So, outside those categories, a size counts only if the merchant declared it:
# `size_source = 'feed'` is that proof, while 'title', 'url' and 'mpn' are
# inferences. The product's category is used rather than the signature's,
# because `enrich` may have corrected it since.
#
# This can neither merge nor split a product — size is not part of
# `identity_hash` — it only changes which variant an offer hangs from. It also
# sharpens the open mega-merge check (docs/roadmap.md), whose discriminator is
# barcodes per *distinct size*: a fitment part wearing invented sizes hides from
# it today.
_SIZE_OF_OFFER = f"""CASE
    WHEN p.category_id NOT IN {_SIZED_CATEGORIES}
         AND coalesce(s.size_source, '') <> 'feed'
    THEN 'TU'
    ELSE {_CANONICAL_SIZE}
END"""

_CREATE_VARIANTS = f"""
INSERT INTO variant (product_id, size_code)
SELECT DISTINCT o.product_id, {_SIZE_OF_OFFER}
FROM raw_offer o
JOIN offer_signature s ON s.raw_offer_id = o.id
JOIN product p ON p.id = o.product_id
LEFT JOIN offer_size_override ovr ON ovr.raw_offer_id = o.id
WHERE o.product_id IS NOT NULL
ON CONFLICT (product_id, size_code) DO NOTHING
"""

_LINK_VARIANTS = f"""
INSERT INTO offer_variant_link (raw_offer_id, variant_id)
SELECT o.id, v.id
FROM raw_offer o
JOIN offer_signature s ON s.raw_offer_id = o.id
JOIN product p ON p.id = o.product_id
LEFT JOIN offer_size_override ovr ON ovr.raw_offer_id = o.id
JOIN variant v ON v.product_id = o.product_id
               AND v.size_code = {_SIZE_OF_OFFER}
WHERE o.product_id IS NOT NULL
ON CONFLICT (raw_offer_id, variant_id) DO NOTHING
"""


def reset_match_state() -> None:
    """Undo every side effect of a previous `match` run — for re-runs during
    development, or if a run needs to be redone with different logic.

    Not a plain TRUNCATE: `TRUNCATE product ... CASCADE` cascades into EVERY
    table with an FK pointing at `product` — including `raw_offer`, which is
    not something a "reset the match" routine should ever touch. (That
    mistake emptied `raw_offer` once during development; recovered from
    `stg_feed_row`, but it should never have happened.)

    Not plain DELETEs either: even with every index in place, `DELETE FROM
    product` (200k+ rows) against a 763k-row `raw_offer` measured 13+ minutes
    in practice — an index makes each FK-check lookup cheap, but 200k of them
    is still 200k round trips. So instead: drop the two FKs that point at
    `product` from tables NOT being emptied (`raw_offer`, `match_override`),
    TRUNCATE the four tables that only reference each other (instant,
    regardless of row count), null the now-dangling pointers, then restore
    both FKs. `match_override` is operator data — its rows survive, only the
    dangling product pointer is cleared. `sql/006` keeps `raw_offer`'s side
    fast for anything else that still needs an index on `product_id`.

    The two FK names are looked up rather than hardcoded: `sql/001_schema.sql`
    declares them inline (no explicit CONSTRAINT name), so Postgres's default
    naming can differ from one build of the schema to the next — hardcoding
    one observed name broke on re-application. Re-created with a fixed,
    explicit name below, so this self-heals to a stable name from here on.
    """
    conn = connect()
    try:
        with conn.cursor() as cur:

            def _fk_name(child_table: str) -> str:
                cur.execute(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = %s::regclass AND confrelid = 'product'::regclass",
                    (child_table,),
                )
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError(
                        f"no FK from {child_table} to product found — is sql/001_schema.sql "
                        "applied to this database?"
                    )
                return row[0]

            raw_offer_fk = _fk_name("raw_offer")
            match_override_fk = _fk_name("match_override")

            cur.execute(f'ALTER TABLE raw_offer DROP CONSTRAINT "{raw_offer_fk}"')
            cur.execute(f'ALTER TABLE match_override DROP CONSTRAINT "{match_override_fk}"')
            cur.execute(
                "TRUNCATE offer_variant_link, variant, product, product_identity_alias "
                "RESTART IDENTITY"
            )
            cur.execute(
                "UPDATE raw_offer SET product_id = NULL, linked_status = 'unresolved', "
                "link_method = NULL, link_confidence = NULL"
            )
            cur.execute(
                "UPDATE match_override SET force_product_id = NULL "
                "WHERE force_product_id IS NOT NULL"
            )
            cur.execute("DELETE FROM match_review_queue WHERE kind = 'gtin_identity_conflict'")
            cur.execute(
                "ALTER TABLE raw_offer ADD CONSTRAINT raw_offer_product_fk "
                "FOREIGN KEY (product_id) REFERENCES product(id)"
            )
            cur.execute(
                "ALTER TABLE match_override ADD CONSTRAINT "
                "match_override_force_product_id_fkey "
                "FOREIGN KEY (force_product_id) REFERENCES product(id)"
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_match() -> MatchResult:
    t0 = time.time()
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_COMPUTE_OFFER_IDENTITY)

            # --- GTIN pass ---
            cur.execute(_BUILD_GTIN_UNITS)
            cur.execute(_FLAG_GTIN_CONFLICTS)
            gtin_conflicts = 0
            for gtin, offer_ids, signals in cur.fetchall():
                cur.execute(
                    """
                    INSERT INTO match_review_queue
                        (kind, review_key, raw_offer_ids, signals, priority)
                    VALUES ('gtin_identity_conflict', %s, %s, %s, 2)
                    ON CONFLICT (kind, review_key) DO UPDATE SET
                        raw_offer_ids = EXCLUDED.raw_offer_ids, signals = EXCLUDED.signals
                    """,
                    (gtin, offer_ids, Jsonb(signals)),
                )
                gtin_conflicts += 1
            cur.execute(
                "UPDATE raw_offer o SET linked_status = 'quarantined' "
                "FROM _gtin_unit gu WHERE o.gtin = gu.gtin AND gu.conflict "
                "AND o.linked_status = 'unresolved'"
            )
            cur.execute(_CREATE_PRODUCTS_FROM_GTIN)
            products_from_gtin = cur.rowcount
            cur.execute(_LINK_GTIN_OFFERS)
            offers_linked_gtin = cur.rowcount

            # --- item_group_id pass (only offers the GTIN pass didn't claim) ---
            cur.execute(_BUILD_ITEM_GROUP_UNITS)
            cur.execute(_CREATE_PRODUCTS_FROM_ITEM_GROUP)
            products_from_ig = cur.rowcount
            cur.execute(_LINK_ITEM_GROUP_OFFERS)
            offers_linked_ig = cur.rowcount

            # --- variants, for every offer either pass linked ---
            cur.execute(_CREATE_VARIANTS)
            variants_created = cur.rowcount
            cur.execute(_LINK_VARIANTS)

        conn.commit()
        return MatchResult(
            products_from_gtin + products_from_ig, variants_created,
            offers_linked_gtin, offers_linked_ig, gtin_conflicts, time.time() - t0,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
