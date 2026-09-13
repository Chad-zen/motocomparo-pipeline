"""Catalogue health, in both directions at once.

Every previous attempt to improve matching was judged on one number: merges
lost. That number only sees the catalogue breaking apart. It is blind to the
opposite failure — products glued together that should not be — which is the
expensive one (docs/product-decisions.md: a false merge costs 10-50x a missed
one). Four of the five attempts recorded in `match.py` were reverted, and none
of them had a way to see what they had broken.

This prints both sides on one screen, so a change can be measured before and
after and judged on the trade it actually makes.

    .venv/Scripts/python.exe ops/mesure_catalogue.py             # print
    .venv/Scripts/python.exe ops/mesure_catalogue.py avant.json  # print + save
    .venv/Scripts/python.exe ops/mesure_catalogue.py apres.json avant.json
                                                                 # print the diff

Read-only. Every query is bounded and the whole run takes under a minute.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RACINE / ".env")

from mcpipe.db import connect  # noqa: E402

# An offer worth counting: the pipeline linked it and the feed still lists it.
VIVANTE = "o.linked_status = 'linked' AND o.is_live AND o.product_id IS NOT NULL"

MESURES: list[tuple[str, str, str]] = [
    # --- volume -------------------------------------------------------------
    ("produits", "volume", "SELECT count(*) FROM product"),
    ("comparables_2m", "volume",
     "SELECT count(*) FROM product_stats WHERE merchant_count >= 2"),
    ("avec_prix", "volume",
     "SELECT count(*) FROM product WHERE min_price IS NOT NULL"),

    # --- ÉCLATEMENT : le catalogue se fragmente ------------------------------
    # A page offering one size is usually the rest of a size run sitting on
    # another page. Counted among comparable products, where it is visible.
    #
    # `TU` is excluded, and that exclusion is the whole measurement: a part
    # with no size legitimately has one entry. Without it this counted every
    # exhaust and saddle as fragmentation and read 12,774 where the real
    # figure is 1,541 — and it called a correction a regression, because
    # dropping invented sizes moves parts into exactly that bucket.
    ("eclat_fiches_1_taille", "eclatement", f"""
        SELECT count(*) FROM (
            SELECT p.id FROM product p
            JOIN product_stats s ON s.product_id = p.id
            JOIN offer_variant_link l ON l.raw_offer_id IN (
                SELECT o.id FROM raw_offer o WHERE o.product_id = p.id AND {VIVANTE})
            JOIN variant v ON v.id = l.variant_id
            WHERE s.merchant_count >= 2
            GROUP BY p.id
            HAVING count(DISTINCT v.size_code) = 1 AND min(v.size_code) <> 'TU'
        ) t"""),
    # Same manufacturer reference, same brand/colour/category, several pages.
    ("eclat_familles_coupees", "eclatement", f"""
        SELECT count(*) FROM (
            SELECT left(o.raw_mpn, 8), p.brand_code, p.colour_code, p.category_id
            FROM raw_offer o JOIN product p ON p.id = o.product_id
            WHERE {VIVANTE} AND o.raw_mpn IS NOT NULL AND length(o.raw_mpn) >= 8
              AND p.colour_code <> 'unknown'
            GROUP BY 1, 2, 3, 4
            HAVING count(DISTINCT o.product_id) > 1
        ) t"""),

    # --- SUR-FUSION : des produits différents collés ensemble ----------------
    # The discriminator from docs/roadmap.md: a real product runs 1-2 barcodes
    # per distinct size. A per-bike fitment part runs dozens, all filed as one
    # size. These three buckets are the alarm, and they must not grow.
    ("fusion_ratio_gte_5", "sur_fusion", f"""
        SELECT count(*) FROM (
            SELECT o.product_id,
                   count(DISTINCT o.gtin)::numeric
                   / greatest(count(DISTINCT v.size_code), 1) AS ratio
            FROM raw_offer o
            LEFT JOIN offer_variant_link l ON l.raw_offer_id = o.id
            LEFT JOIN variant v ON v.id = l.variant_id
            WHERE {VIVANTE} AND o.gtin IS NOT NULL
            GROUP BY o.product_id
        ) t WHERE ratio >= 5"""),
    ("fusion_ratio_gte_20", "sur_fusion", f"""
        SELECT count(*) FROM (
            SELECT o.product_id,
                   count(DISTINCT o.gtin)::numeric
                   / greatest(count(DISTINCT v.size_code), 1) AS ratio
            FROM raw_offer o
            LEFT JOIN offer_variant_link l ON l.raw_offer_id = o.id
            LEFT JOIN variant v ON v.id = l.variant_id
            WHERE {VIVANTE} AND o.gtin IS NOT NULL
            GROUP BY o.product_id
        ) t WHERE ratio >= 20"""),
    ("fusion_pire_nb_gtin", "sur_fusion", f"""
        SELECT coalesce(max(n), 0) FROM (
            SELECT count(DISTINCT o.gtin) AS n FROM raw_offer o
            WHERE {VIVANTE} AND o.gtin IS NOT NULL GROUP BY o.product_id
        ) t"""),
    # Two offers of one merchant on one product carrying the same size: a
    # merchant does not sell the same size of the same article twice, so either
    # the merge is wrong or a borrowed size is.
    ("fusion_doublons_marchand_taille", "sur_fusion", f"""
        SELECT count(*) FROM (
            SELECT o.product_id, o.merchant_id, v.size_code
            FROM raw_offer o
            JOIN offer_variant_link l ON l.raw_offer_id = o.id
            JOIN variant v ON v.id = l.variant_id
            WHERE {VIVANTE} AND v.size_code <> 'TU'
            GROUP BY 1, 2, 3 HAVING count(*) > 1
        ) t"""),
    # A tenfold gap inside one product is rarely a bargain; it is usually two
    # different articles on one page.
    ("fusion_ecart_prix_x10", "sur_fusion", f"""
        SELECT count(*) FROM (
            SELECT o.product_id, min(o.price) AS mini, max(o.price) AS maxi
            FROM raw_offer o
            WHERE {VIVANTE} AND o.price IS NOT NULL AND o.price > 0
            GROUP BY o.product_id HAVING count(*) > 1
        ) t WHERE maxi > 10 * mini"""),

    # --- COHÉRENCE : doit rester à zéro --------------------------------------
    # Mirrors `verify`'s category invariant exactly, including its exclusion of
    # category 25 — the classifier's catch-all, which means "no signal" and is
    # therefore never a disagreement. Without that exclusion this reported
    # 5,360 violations against verify's 0: the instrument was miscalibrated,
    # not the catalogue.
    ("coherence_violations", "coherence", """
        SELECT count(*) FROM (
            SELECT o.product_id FROM raw_offer o
            JOIN offer_signature s ON s.raw_offer_id = o.id
            WHERE o.linked_status = 'linked' AND o.product_id IS NOT NULL
              AND s.category_id != 25
            GROUP BY o.product_id
            HAVING count(DISTINCT s.category_id) > 1
        ) t"""),

    # --- TAILLES -------------------------------------------------------------
    ("tailles_variantes", "tailles", "SELECT count(*) FROM variant"),
    ("tailles_bucket_TU", "tailles", """
        SELECT count(*) FROM offer_variant_link l
        JOIN variant v ON v.id = l.variant_id WHERE v.size_code = 'TU'"""),
]


def releve() -> dict[str, int]:
    conn = connect()
    valeurs: dict[str, int] = {}
    try:
        with conn.cursor() as cur:
            for nom, _groupe, sql in MESURES:
                t0 = time.time()
                cur.execute(sql)
                row = cur.fetchone()
                valeurs[nom] = int(row[0]) if row and row[0] is not None else 0
                print(f"  {nom:34} {valeurs[nom]:>10,}   ({time.time() - t0:.1f}s)")
    finally:
        conn.close()
    return valeurs


def affiche_diff(apres: dict[str, int], avant: dict[str, int]) -> None:
    print("\n  ÉCART AVANT / APRÈS")
    print("  " + "-" * 62)
    for nom, groupe, _sql in MESURES:
        a, b = avant.get(nom), apres.get(nom)
        if a is None or b is None or a == b:
            continue
        ecart = b - a
        # In `eclatement` and `sur_fusion`, down is better. Everywhere else a
        # change is only a fact, so no judgement is printed.
        sens = ""
        if groupe in ("eclatement", "sur_fusion", "coherence"):
            sens = "  mieux" if ecart < 0 else "  PIRE"
        print(f"  {nom:34} {a:>9,} -> {b:>9,}  {ecart:+,}{sens}")
    print()


if __name__ == "__main__":
    print(f"\nMESURE DU CATALOGUE — {time.strftime('%Y-%m-%d %H:%M')}\n")
    valeurs = releve()

    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(valeurs, indent=2), encoding="utf-8")
        print(f"\n  relevé écrit dans {sys.argv[1]}")

    if len(sys.argv) > 2:
        avant = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        affiche_diff(valeurs, avant)
