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
# A spare part says so outright, and then no preposition is needed. Speedway
# lists eleven "Mentonnière HJC RPHA 90S … - Pièces détachées casque" at 90 EUR
# and they sat among 455 EUR modular helmets: the rule above wants "pour casque"
# or "de casque" to overrule the word "casque" in the title, and "Pièces
# détachées casque" has neither.
_IS_A_SPARE_PART = re.compile(r"pieces? detachees?|spare parts?")


# --- pure decisions (offline-testable) -------------------------------------


def decide_override(title: str | None, mapped_category_id: int) -> int | None:
    """Rule 1: corrected category for one coarse-bucket offer, or None to leave
    it alone. Overrides only on a confident title read that changes something."""
    new_id = classify(None, title)
    if new_id in (_UNKNOWN_ID, mapped_category_id):
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
    if _IS_A_SPARE_PART.search(blob):
        return True
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
# Neighbour categories are read the same way `match` will read them (override
# first, then the feed's map), so enrich and match never see two different
# values for the same offer. The override table is emptied at the START of the
# run, so this can only ever see rows written earlier in this same run — never
# leftovers from the previous one, which would make the output depend on what
# happened to be in the table beforehand.
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

# the feed's own Google taxonomy text, one row per merchant SKU. The ORDER BY
# is what makes `DISTINCT ON` deterministic: today every SKU in the bucket has
# exactly one staging row, but a re-`load` could leave two and an arbitrary
# pick would make the run's output depend on physical row order.
_SELECT_GOOGLE_CATEGORIES = """
SELECT DISTINCT ON (row->>'mpn')
       row->>'mpn' AS sku, row->>'google_product_category_text' AS google_cat
FROM stg_feed_row
WHERE merchant_id = %s AND row->>'product_type' = ANY(%s)
ORDER BY row->>'mpn', id DESC
"""


def enrich_categories() -> EnrichResult:
    """Rebuild `offer_category_override` from the closed bucket lists.

    Idempotent: the table is emptied up front and every rule recomputed from
    the feed, inside one transaction — so a re-run always reflects the current
    rules and never the previous run's leftovers, and a failure rolls the whole
    thing back. Must run BEFORE `match`, which reads the overrides when it
    recomputes identities. Each row records WHICH rule wrote it (`source`).
    """
    t0 = time.time()
    conn = connect()
    scanned = 0
    overrides: list[tuple[int, int, str]] = []
    by_rule: dict[str, int] = {}
    try:
        with conn.cursor() as cur:
            # Emptied FIRST, not at the end: the helmet pass below reads this
            # table back (a neighbour's effective category), and reading rows
            # the same run is about to delete would silently mix in whatever
            # the previous run left behind.
            cur.execute("TRUNCATE offer_category_override")

            # --- rule 1: coarse apparel buckets, read from the title ---
            for merchant_code, buckets in _COARSE_BUCKETS.items():
                cur.execute(_SELECT_COARSE, (_UNKNOWN_ID, merchant_code, list(buckets)))
                for offer_id, title, mapped in cur.fetchall():
                    scanned += 1
                    new_id = decide_override(title, mapped)
                    if new_id is not None:
                        overrides.append((offer_id, new_id, "title_reclass"))

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
                    # which step of the cascade decided, in its own order —
                    # stored per row so a suspect correction can be traced back
                    # to the rule that produced it
                    if new_id == _UNKNOWN_ID:
                        rule = (
                            "not_a_moto_helmet"
                            if google_cat and _NOT_A_MOTO_HELMET.search(google_cat)
                            else "helmet_accessory"
                        )
                    elif {c for c in (cats or []) if c in _HELMET_SUBTYPE_IDS}:
                        rule = "helmet_borrowed"
                    else:
                        rule = "helmet_title"
                    overrides.append((offer_id, new_id, rule))

            if overrides:
                cur.executemany(
                    "INSERT INTO offer_category_override "
                    "(raw_offer_id, category_id, source, confidence) "
                    "VALUES (%s, %s, %s, 0.80)",
                    overrides,
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    by_target: dict[int, int] = {}
    for _oid, cid, rule in overrides:
        by_target[cid] = by_target.get(cid, 0) + 1
        by_rule[rule] = by_rule.get(rule, 0) + 1
    return EnrichResult(scanned, len(overrides), by_target, by_rule, time.time() - t0)


# --------------------------------------------------------------- borrowed size

# The letter part of a size, and nothing else. 'XS5354' -> 'XS', 'L59' -> 'L',
# 'M 57/58' -> 'M'. A composite the feed sent as one value ('S/M', '28/30') must
# NOT reduce to its first letter, so the tail after the letters may only be
# empty, or start with a digit (possibly behind one space or parenthesis).
_SIZE_LETTERS = r"^(XXS|XXL|2XL|3XL|4XL|5XL|6XL|XL|XS|S|M|L)([ (]?[0-9].*)?$"

# A barcode that a single merchant puts on several of its own live offers is not
# telling sizes apart at that merchant — the classic "parent EAN" copied across a
# whole size run. Both donor and receiver are vetoed on it: a lone donor holding
# a parent EAN would otherwise agree with itself and hand out a wrong size, and a
# wrong size is worse than none. A dash is honest; an "M" that is really an XL is
# a false claim about a price.
_BORROW_SIZE = f"""
WITH parent_ean AS (
    -- PAS de filtre `is_live` ici, et c'est volontaire : ce bloc detecte un
    -- marchand qui REUTILISE un code-barres sur toute une serie de tailles.
    -- Si l'une des offres de la serie n'est plus en vente, la reutilisation
    -- reste un fait — la restreindre aux offres vivantes affaiblirait la garde
    -- au moment ou elle sert.
    SELECT merchant_id, gtin
    FROM raw_offer
    WHERE gtin IS NOT NULL
    GROUP BY merchant_id, gtin
    HAVING count(*) > 1
),
donors AS (
    SELECT o.gtin,
           -- same spelling the rest of the pipeline uses: textnorm folds XXL
           -- into 2XL, so a borrowed 'XXL' would create a second variant for a
           -- size the product already has
           CASE upper(substring(upper(s.size_code) from '{_SIZE_LETTERS}'))
               WHEN 'XXS' THEN 'XXS'
               WHEN 'XXL' THEN '2XL'
               WHEN 'XXXL' THEN '3XL'
               WHEN 'XXXXL' THEN '4XL'
               ELSE upper(substring(upper(s.size_code) from '{_SIZE_LETTERS}'))
           END AS taille,
           m.code AS merchant,
           s.size_source AS origine
    FROM raw_offer o
    JOIN merchant m ON m.id = o.merchant_id AND m.gtin_trust = 'trusted'
    JOIN offer_signature s ON s.raw_offer_id = o.id
    LEFT JOIN parent_ean pe ON pe.merchant_id = o.merchant_id AND pe.gtin = o.gtin
    -- UN DONNEUR N'A PAS BESOIN D'ETRE ENCORE EN VENTE.
    --
    -- La taille qu'un code-barres designe est une propriete permanente de
    -- l'article : qu'un marchand le stocke encore ou non n'y change rien.
    -- Exiger `o.is_live` sur le donneur jetait donc une preuve valable le jour
    -- ou le donneur quittait son catalogue.
    --
    -- Signale par la proprietaire le 18/09/2026 sur un casque Airoh : Motoblouz
    -- y vendait six declinaisons sans taille, cinq avaient emprunte la leur a
    -- FC-Moto par le code-barres, la sixieme restait « non communiquee ». Son
    -- donneur — le 2XL de FC-Moto, taille declaree dans son flux — avait quitte
    -- la vente le 12 septembre. Le trou se voyait au milieu d'une serie de
    -- tailles du MEME marchand, ce qui ressemble a un bug du site, et en est un.
    --
    -- Mesure avant ecriture : 384 offres sur 237 fiches retrouvent une taille.
    WHERE o.gtin IS NOT NULL AND pe.gtin IS NULL
      -- never borrow a guess: a size read out of a title or a URL is already an
      -- inference, and an inference passed on twice stops being evidence
      AND s.size_source IN ('feed', 'mpn')
      AND s.size_code IS NOT NULL AND s.size_code <> '' AND s.size_code <> 'TU'
      AND upper(s.size_code) ~ '{_SIZE_LETTERS}'
),
agreed AS (
    SELECT gtin,
           min(taille) AS taille,
           count(DISTINCT merchant) AS n,
           string_agg(DISTINCT merchant, ',' ORDER BY merchant) AS qui,
           -- 'feed' seulement si TOUS les donneurs la déclaraient dans leur
           -- flux. Un seul donneur 'mpn' dans le lot suffit à retirer à la
           -- valeur son statut de preuve : hors habillement, `match` la
           -- traitera alors comme une supposition — et c'en est une.
           CASE WHEN bool_and(origine = 'feed') THEN 'feed' ELSE 'mpn' END
               AS origine
    FROM donors
    WHERE taille IS NOT NULL AND taille <> ''
    GROUP BY gtin
    HAVING count(DISTINCT taille) = 1
)
INSERT INTO offer_size_override
    (raw_offer_id, size_code, source, donor_count, donor_codes, donor_source)
SELECT o.id, a.taille, 'xmerchant_gtin', a.n, a.qui, a.origine
FROM raw_offer o
JOIN merchant m ON m.id = o.merchant_id AND m.gtin_trust = 'trusted'
JOIN offer_signature s ON s.raw_offer_id = o.id
JOIN agreed a ON a.gtin = o.gtin
LEFT JOIN parent_ean pe ON pe.merchant_id = o.merchant_id AND pe.gtin = o.gtin
WHERE o.is_live AND o.gtin IS NOT NULL AND pe.gtin IS NULL
  -- On remplit une taille absente, mais aussi une taille SUPPOSÉE. Le titre et
  -- l'URL sont des inférences — on prend le mot qui occupe la place où une
  -- taille se trouve d'habitude, et rien ne garantit que c'en soit une. Ce que
  -- deux marchands déclarent dans leur FLUX sur le même code-barres est une
  -- preuve, et une preuve doit l'emporter sur une supposition.
  --
  -- Sans cette ligne, l'ordre des étapes retournait le raisonnement : le titre
  -- était lu d'abord, l'offre n'était donc plus vide, et l'emprunt la sautait.
  -- Une protection cervicale Alpinestars affichait « taille 2 » — lue dans
  -- « BNS TECH-2 » — alors que six marchands déclaraient XS/M et L/XL sur les
  -- mêmes codes-barres. Signalé par la propriétaire le 14/09/2026.
  AND (s.size_code IS NULL OR s.size_code = '' OR s.size_code = 'TU'
       OR s.size_source IN ('title', 'url'))
ON CONFLICT (raw_offer_id) DO UPDATE SET
    size_code    = EXCLUDED.size_code,
    donor_count  = EXCLUDED.donor_count,
    donor_codes  = EXCLUDED.donor_codes,
    donor_source = EXCLUDED.donor_source,
    confirmed_at = now()
"""


def borrow_sizes() -> int:
    """Fill in a missing size from a merchant selling the same barcode.

    Returns the number of offers that now carry a borrowed size. Abstains
    wherever the evidence is not unanimous — two donors disagreeing, or a
    merchant reusing one barcode across a size run — because the project's rule
    is that a wrong value costs far more than a missing one.
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_BORROW_SIZE)
            written = cur.rowcount
        conn.commit()
        return written
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --- le fourre-tout « Protections », découpé ---------------------------------
#
# Le rayon 11 mélangeait 44 350 offres : ce qui protège le PILOTE (dorsales,
# gilets, coudières, cervicales) et ce qui protège la MOTO (pare-carters, sabots
# moteur, protège-réservoir) — plus, en pratique, des bulles, des garde-boue et
# de la visserie qui n'ont rien à y faire.
#
# Signalé par la propriétaire le 14/09/2026 : sur la fiche d'une protection
# cervicale Alpinestars, l'étagère « dans la même gamme de prix » proposait un
# pare-carter SW-Motech. Même prix, même rayon, aucun rapport — et aucun filtre
# ne pouvait les séparer tant qu'ils portaient le même numéro.
#
# On lit le TITRE MARCHAND, jamais notre nom reconstruit : ce dernier est un sac
# de jetons trié alphabétiquement, il a perdu l'ordre des mots et donc le sens.
#
# Mesuré avant écriture : 71 % des 44 350 offres sont décidées par ces règles.
# Les 29 % restantes — petite visserie, kits de fixation, pièces sans mot-clé —
# restent dans le rayon 11. Une offre laissée où elle est ne casse rien ; une
# offre mal rangée, si.
_PROTECTION_RULES: list[tuple[re.Pattern, int]] = [
    # La protection D'UNE PIÈCE de la moto reste une protection de la moto :
    # « protection de silencieux » n'est pas un échappement. En premier, donc.
    (re.compile(
        r"pare[- ]?carter|crash ?bar|sabot|protege[- ]?reservoir|protection moteur|"
        r"tampon|protection de cadre|insert cadre|slider|protege[- ]?main|"
        r"protections? de radiateur|protege[- ]?disque|protections? de fourche|"
        r"filets? de protection|protections? de disque|couvre[- ]?carter|"
        r"cache[- ]?carter|protection d.axe|protege[- ]?levier|bras oscillant|"
        r"barre de protection|protection (de |du )?(pot|silencieux|collecteur|"
        r"echappement|valve)|pare[- ]?chaleur|grip de reservoir|patin|"
        r"protection laterale|protection de bequille|protections? te de fourche|"
        r"protection de chaine|protege[- ]?chaine|bouchon chassis"), 29),

    (re.compile(
        r"dorsale|gilet de protect|gilet protecteur|coudiere|genouillere|"
        r"protege[- ]?dos|cervicale|neck brace|tour de nuque|col cou|"
        r"plastron|airbag|protection pectorale|protege[- ]?tibia|ceinture lombaire|"
        r"protection poitrine|body armour|veste de protect|protection dorsale|"
        r"protege[- ]?hanche|protection cheville|paire de protections|"
        r"protections? genou|protections? coude|protege[- ]?genou|protege[- ]?coude|"
        r"short de protection|protection lombaire|veste protectrice"), 28),

    # Ce qui n'est pas une protection du tout et a un vrai rayon ailleurs.
    (re.compile(
        r"bulle|saute[- ]?vent|pare[- ]?brise|carenage|tete de fourche|deflecteur|"
        r"garde[- ]?boue|passage de roue|kit plastique|extension de garde|"
        r"leche[- ]?roue|plaque phare|spoiler|aileron"), 18),   # carénage

    (re.compile(
        r"guidon|autocollant|sticker|repose[- ]?pied|planche adhesive|"
        r"film de protection|kit (de )?(fixation|visserie)|silent ?bloc|"
        r"poignees? de maintien|visserie"), 24),                # accessoires
]

_PROTECTION_ID = 11


def protection_subtype_from_title(title: str | None) -> int | None:
    """Le rayon que ce titre désigne vraiment, ou None si aucune règle ne tranche.

    Première règle qui correspond gagne : elles sont rangées du plus spécifique
    au plus général, et la protection d'une pièce mécanique passe avant la pièce
    elle-même.
    """
    blob = tn.norm_txt(title)
    if not blob:
        return None
    for rx, cid in _PROTECTION_RULES:
        if rx.search(blob):
            return cid
    return None


_SELECT_PROTECTIONS = """
SELECT o.id, o.raw_title
FROM raw_offer o
LEFT JOIN offer_category_override ov ON ov.raw_offer_id = o.id
LEFT JOIN category_map cm
    ON cm.merchant_id = o.merchant_id AND cm.raw_path = o.raw_category
WHERE o.is_live
  AND o.raw_title IS NOT NULL
  AND ov.raw_offer_id IS NULL
  AND coalesce(cm.category_id, 0) = %s
"""


def split_protections() -> dict[int, int]:
    """Découpe le fourre-tout « Protections ». Rend {rayon: nombre d'offres}.

    N'écrit que sur les offres qui n'ont PAS déjà une correction : les règles
    précédentes d'`enrich` sont plus spécifiques (casques, reclassement par
    titre) et ne doivent pas être défaites par celle-ci.
    """
    conn = connect()
    par_rayon: dict[int, int] = {}
    try:
        with conn.cursor() as cur:
            cur.execute(_SELECT_PROTECTIONS, (_PROTECTION_ID,))
            lignes = cur.fetchall()

            corrections = []
            for offer_id, titre in lignes:
                cid = protection_subtype_from_title(titre)
                if cid is not None:
                    corrections.append((offer_id, cid, "protection_split"))
                    par_rayon[cid] = par_rayon.get(cid, 0) + 1

            if corrections:
                cur.executemany(
                    "INSERT INTO offer_category_override "
                    "(raw_offer_id, category_id, source, confidence) "
                    "VALUES (%s, %s, %s, 0.80) "
                    "ON CONFLICT (raw_offer_id) DO NOTHING",
                    corrections,
                )
        conn.commit()
        return par_rayon
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --- accorder les marchands sur un même code-barres --------------------------
#
# LA leçon du 2026-09-14, apprise en cassant quelque chose. La découpe
# ci-dessus lit le titre de CHAQUE offre séparément. Or les marchands ne
# nomment pas la même chose pareil :
#
#   Speedway  « Tour De Nuque Alpinestars BNS Tech-2 »   -> reconnu, rayon 28
#   Motoblouz « Protection cervicale Alpinestars BNS »   -> reconnu, rayon 28
#   FC-Moto   « Alpinestars BNS Tech-2 Protecteur de cou » -> aucun mot-clé, 11
#
# Trois marchands, LE MÊME code-barres (8033637210797), deux rayons. Or le rayon
# entre dans l'identité d'une fiche : le pipeline a vu un conflit et a détaché
# les trois. Une fiche à sept marchands est tombée à un.
#
# Un code-barres désigne UN produit. Si une offre de ce code-barres a été
# reconnue, les autres parlent du même objet — quels que soient leurs mots. On
# propage donc la décision, exactement comme `helmet_borrowed` emprunte le
# sous-type d'un casque au voisin qui partage son code-barres.
#
# Deux garde-fous :
#   - on ne propage que si les offres reconnues sont TOUTES D'ACCORD ; deux
#     rayons différents sur un code-barres, c'est une donnée marchande douteuse,
#     pas une décision à trancher au hasard ;
#   - on n'écrase jamais une décision déjà prise par une règle plus spécifique.
_ACCORDER_PAR_GTIN = """
WITH decide AS (
    SELECT o.gtin, ov.category_id
    FROM raw_offer o
    JOIN offer_category_override ov ON ov.raw_offer_id = o.id
    WHERE o.is_live AND o.gtin IS NOT NULL
      AND ov.source = 'protection_split'
),
accord AS (
    SELECT gtin, min(category_id) AS category_id
    FROM decide
    GROUP BY gtin
    HAVING count(DISTINCT category_id) = 1
)
INSERT INTO offer_category_override (raw_offer_id, category_id, source, confidence)
SELECT o.id, a.category_id, 'protection_gtin', 0.75
FROM raw_offer o
JOIN accord a ON a.gtin = o.gtin
LEFT JOIN offer_category_override ov ON ov.raw_offer_id = o.id
WHERE o.is_live AND ov.raw_offer_id IS NULL
ON CONFLICT (raw_offer_id) DO NOTHING
"""


def accorder_protections_par_gtin() -> int:
    """Propage la décision de rayon aux offres du même code-barres. Rend le
    nombre d'offres ralliées."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_ACCORDER_PAR_GTIN)
            n = cur.rowcount
        conn.commit()
        return n
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
