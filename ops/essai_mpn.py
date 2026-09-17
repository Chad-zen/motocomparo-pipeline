"""Essai à blanc de la passe « référence fabricant en préfixe », sans rien écrire.

La passe ne travaille que sur des offres `unresolved` et se contente de les
rattacher à des fiches EXISTANTES : elle peut donc tourner seule, sans refaire
les trois quarts d'heure de `match`. Ce script l'exécute dans une transaction
qu'il annule, compte ce qu'elle ferait, et tire au sort des rapprochements pour
qu'on les juge à la main.

    python ops/essai_mpn.py           # compte + 30 paires au hasard
    python ops/essai_mpn.py 60        # 60 paires
"""

from __future__ import annotations

import os
import sys

import psycopg
from dotenv import dotenv_values

RACINE = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(RACINE, "src"))
from mcpipe.match import _LINK_MPN_PREFIXE  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
env = dotenv_values(os.path.join(RACINE, ".env"))


def main() -> None:
    combien = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    conn = psycopg.connect(env["DATABASE_URL"], autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '900s'")
            cur.execute("CREATE TEMP TABLE _avant AS SELECT id, product_id "
                        "FROM raw_offer WHERE merchant_id IN (4,5) AND is_live")
            cur.execute("CREATE INDEX ON _avant (id)")

            print("exécution de la passe (annulée ensuite) ...", flush=True)
            cur.execute(_LINK_MPN_PREFIXE)
            print(f"  {cur.rowcount:,} offre(s) rattachée(s)".replace(",", " "))

            cur.execute("""
                SELECT count(*),
                       count(DISTINCT o.product_id),
                       count(*) FILTER (WHERE EXISTS (
                           SELECT 1 FROM variant v
                           WHERE v.product_id = o.product_id AND v.size_code <> 'TU'))
                FROM raw_offer o JOIN _avant a ON a.id = o.id
                WHERE a.product_id IS NULL AND o.product_id IS NOT NULL
            """)
            n, fiches, tailles = cur.fetchone()
            print(f"  fiches concernées          : {fiches:,}".replace(",", " "))
            print(f"  dont sur fiche à tailles   : {tailles:,}".replace(",", " "))

            cur.execute("""
                SELECT m.code, count(*) FROM raw_offer o JOIN _avant a ON a.id=o.id
                JOIN merchant m ON m.id=o.merchant_id
                WHERE a.product_id IS NULL AND o.product_id IS NOT NULL
                GROUP BY 1 ORDER BY 2 DESC
            """)
            print("  par marchand :", dict(cur.fetchall()))

            cur.execute("""
                SELECT c.label_fr, count(*) FROM raw_offer o JOIN _avant a ON a.id=o.id
                JOIN product p ON p.id=o.product_id JOIN category c ON c.id=p.category_id
                WHERE a.product_id IS NULL AND o.product_id IS NOT NULL
                GROUP BY 1 ORDER BY 2 DESC LIMIT 8
            """)
            print("  par rayon :")
            for lab, k in cur.fetchall():
                print(f"    {k:>5}  {lab}")

            print(f"\n--- {combien} rapprochements tirés au hasard, à juger ---\n")
            cur.execute("""
                SELECT left(o.raw_title, 52), o.raw_mpn,
                       left(coalesce(p.model_display, ''), 40),
                       (SELECT left(b.raw_title, 52) FROM raw_offer b
                        WHERE b.product_id = o.product_id AND b.merchant_id NOT IN (4,5)
                        ORDER BY b.id LIMIT 1)
                FROM raw_offer o JOIN _avant a ON a.id = o.id
                JOIN product p ON p.id = o.product_id
                WHERE a.product_id IS NULL AND o.product_id IS NOT NULL
                ORDER BY random() LIMIT %s
            """, (combien,))
            for i, (t, mpn, _mod, face) in enumerate(cur.fetchall(), 1):
                print(f"{i:>3}. {t}")
                print(f"     {mpn:<18} -> {face}")
    finally:
        conn.rollback()
        conn.close()
        print("\n(transaction annulée — rien n'a été écrit)")


if __name__ == "__main__":
    main()
