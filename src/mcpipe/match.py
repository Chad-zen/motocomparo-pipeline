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
    # les deux replis d'identité : combien d'unités ont été absorbées
    replis_genre: int = 0
    replis_modele: int = 0
    # doit valoir 0 : voir le filet de stabilité dans `run_match`
    replis_genre_2: int = 0
    # Maxxess + Moto-Axxe rattachés à une fiche existante par identité exacte
    offers_linked_identite: int = 0
    # … et par référence fabricant en préfixe
    offers_linked_mpn: int = 0
    # unités de pièces séparées d'une fiche fourre-tout
    pieces_decoupees: int = 0


# informational identity per offer: category + a hash of the fields that
# would define its product IF it were the sole source of truth. Not used
# below to gate a merge (see module docstring) — kept for `enrich`/a future
# fuzzy stage, and it's cheap (server-side, one pass).
#
# ⚠️ CETTE FORMULE EXISTE À TROIS ENDROITS DANS CE FICHIER, et les trois DOIVENT
# rester identiques, jeton pour jeton : ici, dans `_BUILD_GTIN_UNITS` et dans
# `_BUILD_ITEM_GROUP_UNITS`. Elle avait déjà divergé — cette copie-ci avait
# perdu `category_id` — et c'est resté sans effet tant qu'elle n'était
# qu'informative. Le jour où `_LINK_SANS_GTIN` s'en est servi pour rejoindre une
# fiche, elle comparait un md5 de six champs à un md5 de sept : la passe
# n'aurait rattaché exactement zéro offre, en annonçant un succès.
_COMPUTE_OFFER_IDENTITY = """
UPDATE offer_signature s SET
    category_id = coalesce(ovr.category_id, cm.category_id, 25),
    identity_hash = md5(
        coalesce(s.brand_code, '') || '|' ||
        coalesce(ovr.category_id, cm.category_id, 25)::text || '|' ||
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
couleurs_par_gtin AS (
    SELECT gtin, array_agg(DISTINCT primary_colour) AS couleurs
    FROM members
    WHERE primary_colour IS NOT NULL
    GROUP BY gtin
    HAVING count(DISTINCT primary_colour) > 1
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
    HAVING count(DISTINCT left(genre_age, 1)) FILTER (WHERE left(genre_age, 1) != 'U') > 1
        OR count(DISTINCT right(genre_age, 1)) > 1
        OR count(DISTINCT is_pack) > 1
        OR count(DISTINCT model_year) FILTER (WHERE model_year IS NOT NULL) > 1
        OR count(DISTINCT category_id) FILTER (WHERE category_id != 25) > 1
        OR count(DISTINCT brand_code) FILTER (WHERE brand_code IS NOT NULL) > 1

    UNION

    -- Colour is judged apart from the others, because two colours can differ
    -- without contradicting each other. `{BK}` against `{WH}` is someone being
    -- wrong; `{BK}` against `{BK,SI}` is one merchant naming a two-tone helmet
    -- by one of its colours, and `{BK}` against `{BK|MAT}` is one merchant not
    -- saying the finish. The last two are the same shape — one description
    -- contained in the other — and counting distinct strings could not tell
    -- them apart. Measured before changing it: 7,100 of 10,052 colour
    -- conflicts are inclusions, worth 14,677 offers.
    --
    -- Compatibility is required for EVERY pair, not against a representative:
    -- with `BK`, `BK|MAT` and `BK|GLO` on one barcode, `BK` would otherwise
    -- bridge matte to gloss, and the owner's rule that those are different
    -- products (docs/product-decisions.md) would be broken in practice while
    -- looking intact in the code.
    SELECT gtin FROM couleurs_par_gtin c
    WHERE NOT (
        SELECT bool_and(
               string_to_array(replace(a, '|', '-'), '-')
            @> string_to_array(replace(b, '|', '-'), '-')
            OR string_to_array(replace(b, '|', '-'), '-')
            @> string_to_array(replace(a, '|', '-'), '-'))
        FROM unnest(c.couleurs) a, unnest(c.couleurs) b
    )
    -- A merchant carrying two colours under one barcode is using a "parent"
    -- code covering a range, so its own colour is not evidence about that
    -- barcode. Rare — 17 of 426,782, none on helmets — but it is exactly the
    -- case where inclusion would merge a gloss helmet with a matte one.
    OR EXISTS (
        SELECT 1 FROM members m2
        WHERE m2.gtin = c.gtin AND m2.primary_colour IS NOT NULL
        GROUP BY m2.merchant_id
        HAVING count(DISTINCT m2.primary_colour) > 1
    )
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
        -- the most complete description wins, not whichever member came first:
        -- once `{BK}` and `{BK-SI}` are allowed onto one product, the page must
        -- say "noir et argent", and `(array_agg(...))[1]` would have picked at
        -- random. Longest string = most tokens, since every token adds length.
        (array_agg(m.primary_colour ORDER BY length(m.primary_colour) DESC)
            FILTER (WHERE m.primary_colour IS NOT NULL))[1]
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
-- Tous les jetons qu'un membre du groupe a écrits, pas seulement ceux du
-- représentant. C'est la preuve dont dépend `_FOLD_MODELE` plus bas : un mot
-- que le groupe court a DÉJÀ écrit n'est pas une différence, c'est une
-- information que le tirage du représentant a jetée.
jetons_vus AS (
    SELECT m.gtin, array_agg(DISTINCT t) AS vus
    FROM members m, LATERAL unnest(coalesce(m.model_tokens, '{}'::text[])) t
    GROUP BY m.gtin
),
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
           g.is_pack, w.model_core_ref, w.model_tokens, g.category_id,
           coalesce(jv.vus, '{}'::text[]) AS jetons_vus
    FROM gated g
    JOIN wording w ON w.gtin = g.gtin
    LEFT JOIN jetons_vus jv ON jv.gtin = g.gtin
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

# --- quatrième passe : la référence fabricant, en PRÉFIXE -------------------
#
# Maxxess et Moto-Axxe publient une ligne par COLORIS, jamais par taille. Leur
# `mpn` est donc la référence fabricant amputée du suffixe de taille, souvent
# avec le tiret orphelin resté en place :
#
#     Maxxess   3201725-10-          ->  3201725 10
#     FC-Moto   3201725-10-XXL       ->  3201725 10 XXL
#
# L'une est le PRÉFIXE de l'autre. En égalité stricte on les rate ; en préfixe
# on les attrape. Mesuré : 3 586 offres en égalité, 4 875 en préfixe.
#
# Conséquence à garder en tête pour l'affichage : une ligne Maxxess tombe en
# face de JUSQU'À 32 tailles chez l'autre marchand. Elle ne désigne donc aucune
# taille — elle les couvre toutes, à un prix unique. Le site l'affiche avec
# « taille non précisée », et surtout ne lui en invente pas une.
#
# Dix garde-fous, et aucun n'est décoratif : chacun a été posé après une erreur
# constatée sur un échantillon relu à la main.
_LINK_MPN_PREFIXE = """
-- MATERIALIZED, et ce mot-clé n'est pas décoratif. Sans lui, PostgreSQL a le
-- droit d'aplatir ces deux CTE dans la requête principale, et il en profite
-- deux fois, mal :
--
--   1. `regexp_replace`, qui normalise la référence fabricant, cesse d'être
--      calculé une fois par ligne (~800 000 fois) pour l'être à chaque
--      comparaison de paire — des milliards de fois.
--   2. Le planificateur peut remonter le calcul de recouvrement des jetons
--      AU-DESSUS du test de préfixe. Il paie alors le plus cher des deux
--      filtres en premier, sur toutes les paires de même marque et même rayon.
--
-- C'est ce qui s'est produit le 2026-09-14 : la requête a tourné 50 minutes en
-- n'ayant traité que 1 à 2 % du travail. Fin estimée par le senior : plusieurs
-- dizaines d'heures. Le déclencheur était des statistiques fausses, mais ce
-- mot-clé enlève au planificateur le droit de refaire ce choix.
WITH cle_a AS MATERIALIZED (
    SELECT o.id, o.merchant_id, s.brand_code, s.primary_colour, s.category_id,
           s.genre_age, s.is_pack, coalesce(s.model_tokens, '{}') AS jetons,
           upper(regexp_replace(o.raw_mpn, '[^A-Za-z0-9]', '', 'g')) AS k
    FROM raw_offer o
    JOIN offer_signature s ON s.raw_offer_id = o.id
    JOIN merchant m ON m.id = o.merchant_id AND m.gtin_trust = 'synthetic'
    WHERE o.linked_status = 'unresolved' AND o.is_live
      AND s.brand_code IS NOT NULL
      -- moins de 8 caractères, une référence n'identifie plus rien : 8 825 de
      -- leurs offres sont dans ce cas, et c'est le plafond du catalogue, pas
      -- un défaut de la règle.
      AND length(regexp_replace(o.raw_mpn, '[^A-Za-z0-9]', '', 'g')) >= 8
),
cle_b AS MATERIALIZED (
    SELECT o.product_id, s.brand_code, s.primary_colour, s.category_id,
           s.genre_age, s.is_pack, coalesce(s.model_tokens, '{}') AS jetons,
           upper(regexp_replace(o.raw_mpn, '[^A-Za-z0-9]', '', 'g')) AS k
    FROM raw_offer o
    JOIN offer_signature s ON s.raw_offer_id = o.id
    JOIN merchant m ON m.id = o.merchant_id AND m.gtin_trust <> 'synthetic'
    WHERE o.product_id IS NOT NULL AND o.is_live
      AND s.brand_code IS NOT NULL
      AND length(regexp_replace(o.raw_mpn, '[^A-Za-z0-9]', '', 'g')) >= 8
),
paire AS (
    SELECT a.id, a.merchant_id, b.product_id
    FROM cle_a a
    -- les huit premiers caractères servent de clé de hachage : sans eux, la
    -- relation de préfixe obligerait à comparer chaque offre à toutes.
    JOIN cle_b b ON left(b.k, 8) = left(a.k, 8)
                AND (b.k LIKE a.k || '%' OR a.k LIKE b.k || '%')
    WHERE b.brand_code = a.brand_code                        -- G1
      AND b.category_id = a.category_id                      -- G2
      -- G3 : une couleur absente d'un côté ne contredit rien ; deux couleurs
      -- différentes, si.
      AND (a.primary_colour IS NULL OR b.primary_colour IS NULL
           OR a.primary_colour = b.primary_colour)
      AND a.is_pack = b.is_pack                              -- G8 : unité ≠ lot
      -- G5 : l'âge ne tolère aucun écart (un masque enfant sur une fiche
      -- adulte), le genre tolère l'inconnu, comme partout ailleurs.
      AND right(a.genre_age, 1) = right(b.genre_age, 1)
      AND (left(a.genre_age, 1) = 'U' OR left(b.genre_age, 1) = 'U'
           OR left(a.genre_age, 1) = left(b.genre_age, 1))
      -- G10 : les mots du modèle doivent se recouvrir à 40 %. C'est ce seuil
      -- qui a écarté « Gants cross RAW SHOT » d'une fiche « Gants cross Shot
      -- DRAW » — même référence des deux côtés, deux modèles différents.
      AND cardinality(a.jetons) > 0 AND cardinality(b.jetons) > 0
      AND (SELECT count(*) FROM (
              SELECT unnest(a.jetons) INTERSECT SELECT unnest(b.jetons)) i)::numeric
        / (SELECT count(*) FROM (
              SELECT unnest(a.jetons) UNION SELECT unnest(b.jetons)) u) >= 0.40
    GROUP BY a.id, a.merchant_id, b.product_id
),
-- G4 : une référence qui désigne DEUX fiches ne désigne rien. On s'abstient
-- plutôt que de tirer au sort.
sans_ambiguite AS (
    SELECT id, merchant_id, min(product_id) AS product_id
    FROM paire GROUP BY id, merchant_id HAVING count(*) = 1
),
-- G9 : au plus UNE offre du même marchand par fiche. Sans ça, huit coloris
-- d'un casque s'agglutinaient sur une seule fiche.
retenu AS (
    SELECT DISTINCT ON (product_id, merchant_id) id, product_id
    FROM sans_ambiguite ORDER BY product_id, merchant_id, id
)
UPDATE raw_offer o SET
    product_id = r.product_id, linked_status = 'linked',
    link_method = 'mpn_prefixe', link_confidence = 0.70
FROM retenu r
JOIN product p ON p.id = r.product_id
WHERE o.id = r.id
  AND o.linked_status = 'unresolved'
  AND p.status <> 'merged'
  -- G6 : une fiche sans couleur déterminée est, dans ce catalogue, le symptôme
  -- du défaut ouvert décrit en tête de module — certaines en contiennent
  -- cinquante codes-barres. Y brancher une offre de plus, c'est ajouter du mal
  -- rangé au mal rangé. Coût assumé : environ 1 700 rattachements corrects
  -- laissés de côté.
  AND p.colour_code <> 'unknown'
  -- G3bis : la couleur se juge sur la FICHE, pas sur la paire.
  --
  -- G3, plus haut, compare l'offre entrante à UNE offre de la fiche et tolère
  -- qu'une couleur soit absente d'un côté — c'est voulu : une couleur non
  -- déclarée ne contredit rien. Mais une offre rouge pouvait alors entrer par
  -- la porte d'une offre sans couleur et atterrir sur une fiche par ailleurs
  -- noire. Mesuré le 2026-09-14 : 171 des 177 incohérences relevées par
  -- `mcpipe verify` venaient de là, et 154 des 159 incohérences de couleur
  -- portaient sur une fiche contenant au moins une offre sans couleur.
  --
  -- Le garde-fou raisonnait par paire là où la cohérence se juge sur
  -- l'ensemble. On exige donc que la couleur déclarée par l'offre entrante soit
  -- celle de la fiche visée. Une offre sans couleur reste acceptée : elle ne
  -- contredit toujours rien.
  AND NOT EXISTS (
      SELECT 1 FROM offer_signature s2
      WHERE s2.raw_offer_id = o.id
        AND s2.primary_colour IS NOT NULL
        -- Inclusion, pas égalité. L'égalité stricte a été mesurée le
        -- 2026-09-14 : elle écartait 1 015 rattachements, dont 12 sur 14
        -- relus à la main étaient LÉGITIMES — soit une couleur incluse dans
        -- l'autre (`GN` sur une fiche `BG-GN`, `BK-RD` sur `BK-RD-WH`), soit
        -- le même coloris avec le fini précisé d'un seul côté (`BK|GLO` sur
        -- une fiche `BK`). C'est la règle d'inclusion que le projet applique
        -- déjà ailleurs : `{BK} ⊆ {BK,SI}` ne contredit rien.
        --
        -- Ce qui reste bloqué est la vraie contradiction : `BK-GY-PK` sur une
        -- fiche `BK-BL-PU` — rose contre violet, deux coloris distincts.
        --
        -- Le fini (après la barre verticale) est ignoré : un marchand qui
        -- écrit « mat » et un autre qui ne le dit pas ne se contredisent pas.
        AND NOT (
              string_to_array(split_part(s2.primary_colour, '|', 1), '-')
                <@ string_to_array(split_part(p.colour_code, '|', 1), '-')
           OR string_to_array(split_part(p.colour_code, '|', 1), '-')
                <@ string_to_array(split_part(s2.primary_colour, '|', 1), '-')
        )
  )
"""



# --- les deux replis d'identité ----------------------------------------------
#
# Ces deux passes tournent APRÈS `_BUILD_GTIN_UNITS` et AVANT la création des
# fiches. Elles ne fusionnent rien elles-mêmes : elles réécrivent
# l'`identity_hash` d'une unité pour celui d'une autre, et le reste du module
# fait déjà le travail — « des unités qui se réduisent au même hash sont le même
# produit » (voir l'en-tête du module).
#
# Les champs d'identité du gagnant sont recopiés en même temps que son hash,
# sinon `DISTINCT ON (identity_hash)` pourrait décrire la fiche avec les valeurs
# de l'unité absorbée.
#
# Portée : les unités GTIN seulement. C'est là que le défaut a été mesuré (un
# code-barres par taille, donc une taille par fiche), et les unités
# `item_group` sont déjà propres à un seul marchand.

# La clé commune aux deux replis : l'identité, amputée du champ que la passe
# autorise à varier. Même expression que l'`identity_hash`, pour qu'elles ne
# puissent pas diverger.
_CLE_SANS_GENRE = """
    coalesce(brand_code, '') || '|' || category_id::text || '|' ||
    coalesce(primary_colour, '') || '|' || coalesce(model_year::text, '') || '|' ||
    is_pack::int::text || '|' || coalesce(model_core_ref, '') || ':' ||
    coalesce(array_to_string(model_tokens, '-'), '') || '|' || right(genre_age, 1)
"""

_CLE_SANS_JETONS = """
    coalesce(brand_code, '') || '|' || category_id::text || '|' ||
    coalesce(primary_colour, '') || '|' || coalesce(model_year::text, '') || '|' ||
    coalesce(genre_age, '') || '|' || is_pack::int::text || '|' ||
    coalesce(model_core_ref, '')
"""

# 1. « Le flux n'a rien dit » n'est pas « un autre genre ».
#
# Cas mesuré le 14/09/2026 : la veste Ixon Madden jaune, sept tailles, sept
# codes-barres. FC-Moto déclare `male` sur les trois tailles qu'il vend, La
# Bécanerie ne déclare rien sur les quatre autres — deux fiches pour une veste.
# `match` traitait déjà `U` comme « aucune preuve » À L'INTÉRIEUR d'un
# code-barres ; le défaut apparaissait ENTRE codes-barres, au moment de former
# l'identité.
#
# `d.n = 1` est le garde-fou : s'il existe à la fois un « homme » et une
# « femme » sous la même clé, personne n'absorbe personne. Un vêtement décliné
# en coupe homme et coupe femme reste deux produits, et c'est correct.
# La base des deux replis, matérialisée et indexée. En CTE, la même clé texte
# était recalculée et rejointe trois fois : mesuré à plus de cinq minutes sur
# 400 000 unités, avec débordement sur disque. Table + index : quelques
# secondes, et le `--reset` complet ne s'allonge pas.
_PREP_REPLI_GENRE = f"""
CREATE TEMP TABLE _repli_g ON COMMIT DROP AS
SELECT gtin, identity_hash, genre_age, ({_CLE_SANS_GENRE}) AS cle
FROM _gtin_unit WHERE NOT conflict;
CREATE INDEX ON _repli_g (cle);
ANALYZE _repli_g;
"""

_FOLD_GENRE = """
WITH base AS (SELECT * FROM _repli_g),
declares AS (
    SELECT cle, count(DISTINCT left(genre_age, 1))
               FILTER (WHERE left(genre_age, 1) <> 'U') AS n
    FROM base GROUP BY cle
),
gagnant AS (
    SELECT DISTINCT ON (cle) cle, genre_age AS genre_gagnant,
           identity_hash AS hash_gagnant
    FROM base WHERE left(genre_age, 1) <> 'U'
    ORDER BY cle, gtin
)
UPDATE _gtin_unit u
SET genre_age = g.genre_gagnant, identity_hash = g.hash_gagnant
FROM base b
JOIN declares d ON d.cle = b.cle
JOIN gagnant  g ON g.cle = b.cle
WHERE u.gtin = b.gtin
  AND left(b.genre_age, 1) = 'U'
  AND d.n = 1
"""

# 2. Un nom de modèle moins bavard n'est pas un autre modèle — à une condition.
#
# La règle naïve (« les jetons de l'une inclus dans ceux de l'autre ») a été
# mesurée sur 25 paires tirées au sort après le filtrage le plus serré possible :
# 11 fausses fusions sur 25. Un mot en plus, c'est aussi bien du bavardage
# (« Solid ») qu'un produit différent (« Padded », « Camo », « fumé », « sans
# rétroviseurs »), et aucun filtre de forme ne sait les distinguer — pas même le
# préfixe du code-barres, puisque 60 % des préfixes à 11 chiffres portent déjà
# des couleurs différentes : un bloc d'EAN, c'est une famille, pas un produit.
#
# Le prédicat retenu ne juge pas le mot, il demande une PREUVE : les jetons en
# plus doivent déjà figurer dans ce qu'un marchand de l'unité courte a écrit.
# Ce n'est alors plus « un titre plus bavard », c'est « une information que
# l'unité possède et que le tirage du représentant a jetée ».
#
# Mesuré sur la base vive : 575 paires, 4 391 offres re-rassemblées, 98 %
# d'équipement, 0 fausse fusion sur 25 paires relues une par une. Le cas
# fondateur (Arai SZ-R VAS EVO Solid) est retenu ; les deux pièges de génération
# du même Arai (VAS contre VAS EVO) sont exclus, parce qu'aucun marchand du VAS
# n'écrit jamais « evo ».
#
# Le repli se fait sur le MAXIMUM du groupe, jamais de proche en proche : avec
# A ⊂ B ⊂ C, B ne sert pas de pont, le prédicat doit tenir de A vers C
# directement.
_PREP_REPLI_MODELE = f"""
CREATE TEMP TABLE _repli_m ON COMMIT DROP AS
SELECT gtin, identity_hash, model_tokens, jetons_vus,
       ({_CLE_SANS_JETONS}) AS cle
FROM _gtin_unit
WHERE NOT conflict AND model_tokens IS NOT NULL
  AND cardinality(model_tokens) >= 2
  -- La restriction aux unités portant une RÉFÉRENCE de modèle a été LEVÉE le
  -- 2026-09-14, après mesure. Elle était prudente et documentée : sans elle, le
  -- seau (marque, catégorie, couleur, année, genre) contient aussi les titres
  -- génériques — « Ermax Bulle Haute » et sa famille — où élire le titre le plus
  -- long risquait de grossir la méga-fusion connue.
  --
  -- Ce qu'elle coûtait, signalé par la propriétaire : deux fiches Arai SZ-R VAS
  -- EVO, cinq tailles du même casque, quatre sur l'une et la cinquième seule sur
  -- l'autre parce qu'un marchand qui ne vend QUE cette taille écrit un titre
  -- plus court. Aucune des deux n'a de référence de modèle, donc la règle ne les
  -- voyait jamais — alors que le prédicat les accepte : « solid » figure bien
  -- dans ce que Motoblouz écrit sur ce code-barres.
  --
  -- Mesuré à blanc (`ops/essai_repli_modele_elargi.py`) : +126 fiches recollées,
  -- +806 offres re-rassemblées, 386 fusions ajoutées, **plus gros groupe
  -- inchangé à 1 314** — la méga-fusion redoutée ne grossit pas d'une unité.
  -- 30 fusions relues une par une : aucune fausse. Les deux qui semblaient
  -- douteuses (Nolan X-804 RS « Ultra », Shima « X-Breeze 2 ») se sont révélées
  -- justes — le mot en plus est écrit par un autre marchand sur le MÊME
  -- code-barres, et un code-barres est un produit.
  ;
CREATE INDEX ON _repli_m (cle);
CREATE INDEX ON _repli_m (identity_hash);
ANALYZE _repli_m;
"""

_FOLD_MODELE = """
WITH base AS (SELECT * FROM _repli_m),
maxi AS (
    SELECT DISTINCT ON (cle) cle, gtin AS gtin_gagnant,
           model_tokens AS jetons_gagnant, identity_hash AS hash_gagnant
    FROM base
    ORDER BY cle, cardinality(model_tokens) DESC, gtin
)
UPDATE _gtin_unit u
SET model_tokens = m.jetons_gagnant, identity_hash = m.hash_gagnant
FROM base b
JOIN maxi m ON m.cle = b.cle
WHERE u.gtin = b.gtin
  AND b.gtin <> m.gtin_gagnant
  -- inclusion STRICTE : deux unités aux jetons identiques portent déjà le même
  -- hash, les « replier » ne ferait qu'écrire la valeur qu'elles ont, et
  -- gonflerait le compteur de replis avec des non-événements.
  AND b.model_tokens <@ m.jetons_gagnant
  AND NOT (m.jetons_gagnant <@ b.model_tokens)
  -- La preuve : chaque jeton en plus figure déjà dans ce que l'unité courte a
  -- écrit. `jetons_vus` est l'UNION de ses membres — deux marchands peuvent donc
  -- fournir la preuve à eux deux, ce qu'aucun titre seul ne contenait. C'est la
  -- forme qui a été mesurée (0 fausse fusion sur 25 relues), pas une forme plus
  -- faible qu'on se serait permise après coup.
  AND NOT EXISTS (
      SELECT 1 FROM unnest(m.jetons_gagnant) x
      WHERE NOT (x = ANY(b.model_tokens)) AND NOT (x = ANY(b.jetons_vus))
  )
  -- TOUT LE GROUPE OU RIEN. Sans ceci, le repli du genre pouvait être défait :
  -- deux unités venant d'être réunies sur un même hash n'ont pas le même
  -- `jetons_vus`, l'une partait rejoindre le gagnant et l'autre restait — les
  -- sept tailles de la veste Ixon Madden se rescindaient en deux fiches, après
  -- qu'une passe les avait justement rassemblées. Une unité ne bouge donc que si
  -- toutes celles qui partagent son hash peuvent bouger avec elle.
  -- `_repli_m` et non `base` : une CTE référencée plusieurs fois est
  -- matérialisée par Postgres, et la table matérialisée n'a pas d'index — la
  -- sous-requête devenait un balayage complet PAR LIGNE. En visant la table,
  -- l'index sur `identity_hash` sert.
  AND NOT EXISTS (
      SELECT 1 FROM _repli_m b2
      WHERE b2.identity_hash = b.identity_hash
        AND EXISTS (
            SELECT 1 FROM unnest(m.jetons_gagnant) x
            WHERE NOT (x = ANY(b2.model_tokens)) AND NOT (x = ANY(b2.jetons_vus))
        )
  )
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

# --- troisième passe : les marchands sans code-barres fiable -----------------
#
# Maxxess et Moto-Axxe (`gtin_trust='synthetic'`) n'ont ni code-barres utilisable
# ni `item_group_id` : leurs offres restaient `unresolved` de bout en bout, soit
# 8 757 casques invisibles sur le site alors que les autres marchands vendent
# les mêmes.
#
# Ce n'est PAS un rapprochement approximatif, et c'est délibéré. La règle est :
#
#   une offre rejoint une fiche EXISTANTE quand son identité, calculée
#   exactement comme celle de n'importe quelle autre offre, lui est identique.
#
# Trois verrous, chacun contre une façon connue de se tromper :
#
# 1. **Jamais de création.** Ces offres ne peuvent que REJOINDRE une fiche qu'un
#    marchand à code-barres fiable a déjà établie. Une source non vérifiée
#    n'invente donc aucune fiche ; au pire elle n'en rejoint aucune.
# 2. **`model_core_ref IS NOT NULL`.** C'est le garde-fou contre le défaut connu
#    du module (voir l'en-tête) : un titre générique sans référence — « Ermax
#    Bulle Haute » — partage son identité avec des centaines de pièces qui n'ont
#    rien à voir. Une référence de modèle explicite est la preuve qu'il manque.
# 3. **`model_strength = 'strong'`.** Un titre mal lu ne sert pas de clé.
#
# Une offre qui ne passe pas ces trois verrous reste `unresolved`, comme avant :
# invisible vaut mieux que mal rangée.
_LINK_SANS_GTIN = """
UPDATE raw_offer o SET
    product_id = p.id, linked_status = 'linked',
    link_method = 'identite', link_confidence = 0.80
FROM offer_signature s
JOIN product p ON p.identity_hash = s.identity_hash
WHERE o.id = s.raw_offer_id
  -- La vraie définition du problème, pas deux identifiants écrits en dur : un
  -- marchand dont le code-barres est fabriqué n'a pas de clé utilisable.
  --
  -- En EXISTS et non en JOIN : PostgreSQL refuse qu'on référence la table mise
  -- à jour (`o`) dans la condition d'une jointure du FROM. Écrit en JOIN, ce
  -- bloc a fait échouer un `match` de trente-cinq minutes à sa dernière
  -- instruction, et la transaction a tout annulé.
  AND EXISTS (
      SELECT 1 FROM merchant mm
      WHERE mm.id = o.merchant_id AND mm.gtin_trust = 'synthetic'
  )
  AND o.linked_status = 'unresolved'
  -- `model_core_ref IS NOT NULL` protège du bug ouvert du module non pas par
  -- vertu propre, mais parce que la référence entre dans l'empreinte : une
  -- fiche à titre générique n'a pas la même, donc on ne peut pas la rejoindre.
  AND s.model_core_ref IS NOT NULL
  AND s.model_strength = 'strong'
  AND s.category_id <> 25
  AND p.status <> 'merged'
  -- Le même verrou opérateur que la passe GTIN : quelqu'un qui a séparé un
  -- produit à la main ne doit pas voir un marchand sans code-barres l'y remettre.
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
# Une taille EMPRUNTÉE PAR CODE-BARRES à un marchand qui la déclare dans son
# flux échappe à cette règle, et c'est la seule exception. Ce n'est pas une
# inférence de plus : c'est la même déclaration, relayée par l'identifiant sur
# lequel tous les marchands sont d'accord. `donor_source` ne vaut 'feed' que si
# TOUS les donneurs la déclaraient — un seul donneur 'mpn' suffit à la faire
# retomber dans les suppositions.
#
# Sans cette exception, sur la housse Ixon Blanky (rayon Entretien), quatorze
# offres sur dix-huit s'affichaient « taille non communiquée » alors que leurs
# codes-barres correspondaient un à un à ceux de FC-Moto, qui déclare M, L, XL
# et 2XL. Le filtre de taille ne filtrait donc plus rien et le même marchand
# revenait quatre fois. Signalé par la propriétaire le 17/09/2026 ; portée
# mesurée avant correction : 1 079 offres sur 325 fiches, toutes comparables.
_SIZE_OF_OFFER = f"""CASE
    WHEN p.category_id NOT IN {_SIZED_CATEGORIES}
         AND coalesce(s.size_source, '') <> 'feed'
         AND coalesce(ovr.donor_source, '') <> 'feed'
    THEN 'TU'
    ELSE {_CANONICAL_SIZE}
END"""

# --- la découpe des fiches fourre-tout de pièces ----------------------------
#
# LE défaut ouvert du module, enfin traité — et c'est la cinquième tentative,
# les quatre précédentes ayant été annulées. Ce qui change ici est le critère.
#
# Le cas : « Amortisseur Ohlins Arrière », **534 codes-barres sur une fiche**.
# « Platine GPR Tech », 77. Un support de sacoches SW-Motech qui mélange le
# montage Triumph à 330 € et le montage Yamaha à 635 €. Le visiteur lit « dès
# 330 € » pour une pièce qui ne va pas sur sa moto : ce n'est pas une
# comparaison, c'est une erreur d'aiguillage.
#
# Mesuré sur ces fiches : sur 72 668 offres présentées comme comparées, **1 259
# le sont vraiment**. Les 71 386 autres sont des produits uniques empilés.
#
# Les trois conditions, et pourquoi aucune ne peut sauter :
#
# 1. `model_core_ref IS NULL` — une référence de modèle explicite suffit à
#    distinguer les produits, la fiche n'est pas un fourre-tout.
# 2. **Hors habillement.** C'est la condition qui manquait aux tentatives
#    précédentes. Dans les rayons où la taille est un vrai attribut, plusieurs
#    codes-barres pour une seule taille veut dire « les tailles n'ont pas été
#    lues », pas « plusieurs produits » — échantillon à l'appui : des demi-bottes
#    Fox, un casque Scorpion et un casque Shot enfant passaient à la découpe
#    sans ce garde-fou.
# 3. **Trois codes-barres par taille distincte.** Un vrai produit tourne autour
#    de un ; ces fiches-là montent à 534.
#
# Vérifié : 12 fiches tirées au hasard après ces trois conditions, 12 pièces à
# montage spécifique (câbles de gaz, kit piston, support de plaque Ermax,
# platine GPR, pédale de frein). Aucun vêtement.
#
# Ce que ça coûte, assumé : 71 386 offres passent sur des fiches à un seul
# marchand et sortent donc des listes. Elles restent accessibles par leur
# adresse. Décision de l'exploitante, prise sur ces chiffres.

# Les rayons où une taille est un vrai attribut de l'article. Volontairement
# LARGE : mieux vaut épargner une fiche de pièces que casser un vrai produit.
_RAYONS_HABILLEMENT = "(1,2,3,4,5,6,7,8,9,10,23,26,27)"

_SPLIT_PIECES = f"""
WITH par_offre AS (
    SELECT u.gtin, u.identity_hash,
           CASE
               WHEN u.category_id NOT IN {_SIZED_CATEGORIES}
                    AND coalesce(s.size_source, '') <> 'feed'
                    AND coalesce(ovr.donor_source, '') <> 'feed'
               THEN 'TU'
               ELSE coalesce(nullif(s.size_code, ''), ovr.size_code, 'TU')
           END AS taille
    FROM _gtin_unit u
    JOIN raw_offer o ON o.gtin = u.gtin
    JOIN offer_signature s ON s.raw_offer_id = o.id
    LEFT JOIN offer_size_override ovr ON ovr.raw_offer_id = o.id
    WHERE NOT u.conflict
      AND u.model_core_ref IS NULL
      AND u.category_id NOT IN {_RAYONS_HABILLEMENT}
),
groupe AS (
    SELECT identity_hash,
           count(DISTINCT gtin)   AS codes_barres,
           count(DISTINCT taille) AS tailles
    FROM par_offre GROUP BY 1
)
UPDATE _gtin_unit u
-- l'identité devient propre au code-barres : une fiche par pièce réelle.
SET identity_hash = md5(u.identity_hash || '|' || u.gtin)
FROM groupe g
WHERE g.identity_hash = u.identity_hash
  AND g.codes_barres::numeric / g.tailles >= 3
"""




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


# Les liens devenus faux, et EUX SEULS : un lien dont la variante ne porte plus
# la taille que l'offre déclare aujourd'hui. `_LINK_VARIANTS` insère sans
# écraser (`ON CONFLICT DO NOTHING`), donc sans ce ménage l'offre se
# retrouverait rattachée à DEUX tailles — l'ancienne et la nouvelle — et la
# fiche en choisirait une au hasard.
_DELIER_TAILLES_PERIMEES = f"""
DELETE FROM offer_variant_link l
USING raw_offer o
     JOIN product p ON p.id = o.product_id
     JOIN offer_signature s ON s.raw_offer_id = o.id
     LEFT JOIN offer_size_override ovr ON ovr.raw_offer_id = o.id,
     variant v
WHERE l.raw_offer_id = o.id
  AND v.id = l.variant_id
  AND v.size_code <> ({_SIZE_OF_OFFER})
"""


def relink_sizes() -> dict[str, int]:
    """Recalculer les VARIANTES seules, sans refaire tout l'appariement.

    Les fiches et leurs offres ne bougent pas ici : seules changent les tailles
    qui leur sont rattachées. C'est utile parce que les deux étapes qui les
    construisent — `_CREATE_VARIANTS` et `_LINK_VARIANTS` — ne dépendent que de
    `raw_offer.product_id`, de la signature et des tailles empruntées. Aucune de
    ces trois choses n'est touchée par l'appariement lui-même.

    Sans cette étape, corriger une règle de taille coûtait un `match --reset`
    complet : cinquante minutes, site éteint, et tout le catalogue reconstruit
    pour changer une colonne. Ici, ce sont les MÊMES instructions que celles du
    `match`, dans le même ordre — pas une réécriture parallèle qui finirait par
    diverger de l'originale.

    Rejouable sans risque : la suppression ne vise que les liens devenus faux,
    et les deux insertions sont idempotentes.
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_DELIER_TAILLES_PERIMEES)
            delies = cur.rowcount
            cur.execute(_CREATE_VARIANTS)
            creees = cur.rowcount
            cur.execute(_LINK_VARIANTS)
            liees = cur.rowcount
        conn.commit()
        # Trois tables réécrites en masse : sans ANALYZE, le planificateur
        # garde les statistiques d'avant et choisit des plans faux sur les
        # requêtes qui les lisent. Trois pannes le 14/09/2026 pour cette seule
        # raison.
        with conn.cursor() as cur:
            cur.execute("ANALYZE variant")
            cur.execute("ANALYZE offer_variant_link")
        return {"delies": delies, "variantes_creees": creees, "liens_crees": liees}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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


def run_match(*, avec_mpn: bool = True) -> MatchResult:
    """Rapproche les offres en fiches produits.

    `avec_mpn=False` laisse de côté la passe « référence fabricant en préfixe »,
    qui rattache Maxxess et Moto-Axxe à des fiches existantes. Elle est la seule
    passe du `match` dont le coût ne soit pas borné : elle a dépassé 50 minutes
    le 2026-09-14, contre 413 s mesurées hors transaction.

    La sortir n'abîme rien, parce qu'elle est monotone : elle ne lit que des
    offres `unresolved`, ne les rattache qu'à des fiches qui existent déjà, et
    n'en crée aucune. `ops/appliquer_mpn.py` la rejoue à l'identique — mêmes
    instructions, importées de ce module — sur la base validée, donc sur des
    statistiques fraîches. Faire ainsi rend le `match` prévisible et isole le
    seul morceau qui ne l'est pas.

    Après un `match(avec_mpn=False)` suivi de `ops/appliquer_mpn.py`, il faut
    relancer `mcpipe verify` : celui de la commande `match` aura contrôlé un
    catalogue auquel il manquait encore les rattachements de cette passe.
    """

    t0 = time.time()
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_COMPUTE_OFFER_IDENTITY)

            # --- GTIN pass ---
            cur.execute(_BUILD_GTIN_UNITS)

            # Indexée et analysée avant toute chose : une table temporaire n'a ni
            # statistiques ni index, et les replis la mettent à jour en la
            # rejoignant sur `gtin`. Sans ça le planificateur peut choisir une
            # boucle imbriquée sur 400 000 lignes — la forme de plan qui
            # transforme « quelques secondes » en « une demi-heure » au milieu
            # d'une transaction. Le banc d'essai mesure sur une copie indexée ;
            # la production doit voir la même chose, sinon la mesure ne vaut rien.
            cur.execute("CREATE INDEX ON _gtin_unit (gtin)")
            cur.execute("ANALYZE _gtin_unit")

            # Les deux replis d'identité, dans cet ordre : le genre d'abord,
            # parce que la clé du repli des jetons contient `genre_age`.
            #
            # Ils ne sont PAS indépendants, et le prétendre serait faux : le
            # premier réécrit le champ sur lequel le second construit sa clé. Une
            # unité passée de « genre inconnu » à « homme » entre donc dans un
            # seau où elle n'entrait pas, et peut s'y replier. C'est voulu —
            # normaliser d'abord, comparer ensuite — et ce n'est pas dangereux :
            # le prédicat du second repli est évalué sur les preuves propres de
            # l'unité, jamais sur celles de son nouveau voisin.
            cur.execute(_PREP_REPLI_GENRE)
            cur.execute(_FOLD_GENRE)
            replis_genre = cur.rowcount
            # préparée APRÈS le repli du genre : sa clé contient `genre_age`,
            # et doit donc voir le genre déjà normalisé.
            cur.execute(_PREP_REPLI_MODELE)
            cur.execute(_FOLD_MODELE)
            replis_modele = cur.rowcount

            # Filet : le repli du genre doit être STABLE, c'est-à-dire qu'un
            # second passage après le repli des jetons ne doit plus rien trouver.
            # S'il trouve quelque chose, c'est que le second repli a séparé des
            # unités que le premier venait de réunir — le défaut que la règle
            # « tout le groupe ou rien » est censée interdire. Le chiffre est
            # remonté plutôt qu'ignoré : un filet silencieux ne sert à rien.
            cur.execute("DROP TABLE IF EXISTS _repli_g")
            cur.execute(_PREP_REPLI_GENRE)
            cur.execute(_FOLD_GENRE)
            replis_genre_2 = cur.rowcount

            # La découpe passe APRÈS les replis (qui rassemblent) et AVANT la
            # création des fiches : elle ne défait donc rien, elle sépare ce qui
            # n'aurait jamais dû être ensemble.
            cur.execute(_SPLIT_PIECES)
            pieces_decoupees = cur.rowcount

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

            # --- troisième passe : Maxxess et Moto-Axxe rejoignent des fiches
            #     existantes, sans jamais en créer (voir _LINK_SANS_GTIN) ---
            cur.execute(_LINK_SANS_GTIN)
            offers_linked_identite = cur.rowcount

            # Initialisé AVANT le test : sous `--sans-mpn`, le compteur n'était
            # affecté nulle part et le résumé final levait une UnboundLocalError
            # — après le commit, donc sans rien perdre, mais la commande sortait
            # en erreur sur un passage réussi et l'ANALYZE d'après coup, placé
            # plus bas, ne tournait pas. C'est justement celui dont l'absence
            # nous a coûté deux heures le 2026-09-14.
            offers_linked_mpn = 0

            # --- quatrième passe : la référence fabricant en préfixe ---
            # Elle passe APRÈS l'identité exacte, qui est plus sûre et garde
            # donc ses rattachements.
            #
            # ANALYZE d'abord, et ce n'est pas du confort. Les trois passes
            # ci-dessus viennent de réécrire `linked_status` et `product_id`
            # sur tout `raw_offer` ; les statistiques du planificateur datent
            # d'avant. Il sous-estime alors le nombre de paires candidates et
            # choisit un plan qui évalue le recouvrement de jetons — deux
            # sous-requêtes par paire — beaucoup trop souvent.
            #
            # Mesuré : cette requête prend 413 s lancée seule sur une base aux
            # statistiques fraîches (ops/appliquer_mpn.log, 2026-09-12). Dans le
            # `match --reset` du 2026-09-14 elle a dépassé 50 minutes sans
            # montrer de fin, et a dû être annulée.
            #
            # `product` est la table qui compte, et c'est celle qu'on avait
            # d'abord oubliée : l'autoanalyse de PostgreSQL est passée juste
            # après le TRUNCATE du `--reset` et a enregistré « table vide ». À
            # l'intérieur de la transaction, le planificateur estimait donc
            # `product` à 0 ligne alors qu'elle en portait 244 000 non validées
            # — et l'UPDATE final joint précisément `product`. Une erreur d'un
            # facteur 244 000 sur la table pivot.
            #
            # Même famille que `freshness`, passé de 39 minutes à 125 s après un
            # ANALYZE. Dix secondes ici.
            cur.execute("ANALYZE raw_offer")
            cur.execute("ANALYZE offer_signature")
            cur.execute("ANALYZE product")
            if avec_mpn:
                cur.execute(_LINK_MPN_PREFIXE)
                offers_linked_mpn = cur.rowcount

            # --- variants, for every offer either pass linked ---
            cur.execute(_CREATE_VARIANTS)
            variants_created = cur.rowcount
            cur.execute(_LINK_VARIANTS)

        conn.commit()

        # ANALYZE après coup, hors transaction : un rematch complet réécrit
        # `product_id` sur 600 000 lignes et `product` en entier, donc les
        # statistiques du planificateur ne valent plus rien. Mesuré le
        # 14/09/2026 : `freshness` a tourné 39 minutes sans finir, puis 125
        # secondes après cet ANALYZE. Trois tables, dix secondes.
        with connect() as c2:
            c2.autocommit = True
            for table in ("raw_offer", "product", "offer_signature", "variant"):
                c2.execute(f"ANALYZE {table}")
        return MatchResult(
            products_from_gtin + products_from_ig, variants_created,
            offers_linked_gtin, offers_linked_ig, gtin_conflicts, time.time() - t0,
            replis_genre=replis_genre, replis_modele=replis_modele,
            replis_genre_2=replis_genre_2,
            offers_linked_identite=offers_linked_identite,
            offers_linked_mpn=offers_linked_mpn,
            pieces_decoupees=pieces_decoupees,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
