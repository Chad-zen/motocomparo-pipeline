"""Applique la passe « référence fabricant en préfixe », sans refaire tout `match`.

La passe est désormais dans `run_match`, donc elle repartira toute seule au
prochain passage complet. Ce script existe pour l'appliquer MAINTENANT sans
repayer les trois quarts d'heure : elle ne touche que des offres `unresolved` et
se contente de les rattacher à des fiches qui existent déjà. Rien d'autre dans
le catalogue ne bouge.

À lancer une seule fois. Ensuite, `mcpipe freshness` est obligatoire : c'est lui
qui recalcule les prix de tête et rafraîchit `product_stats`, d'où sortent tous
les prix affichés en liste.

    python ops/appliquer_mpn.py
"""

from __future__ import annotations

import os
import sys
import time

import psycopg
from dotenv import dotenv_values

RACINE = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(RACINE, "src"))
from mcpipe.match import _LINK_MPN_PREFIXE  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
env = dotenv_values(os.path.join(RACINE, ".env"))


def main() -> None:
    conn = psycopg.connect(env["DATABASE_URL"], autocommit=False)
    t0 = time.time()
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '1800s'")
            avant = cur.execute(
                "SELECT count(*) FROM raw_offer WHERE merchant_id IN (4,5) "
                "AND linked_status = 'linked' AND is_live").fetchone()[0]
            print(f"offres Maxxess/Moto-Axxe rattachées avant : {avant}", flush=True)

            print("application de la passe ...", flush=True)
            cur.execute(_LINK_MPN_PREFIXE)
            n = cur.rowcount
            print(f"  {n:,} offre(s) rattachée(s)".replace(",", " "), flush=True)

            # Les variantes : une offre sans taille se range dans la variante
            # 'TU', que le site n'affiche jamais comme un bouton de taille.
            from mcpipe.match import _CREATE_VARIANTS, _LINK_VARIANTS
            cur.execute(_CREATE_VARIANTS)
            print(f"  {cur.rowcount:,} variante(s) créée(s)".replace(",", " "))
            cur.execute(_LINK_VARIANTS)

        conn.commit()
        with conn.cursor() as cur:
            apres = cur.execute(
                "SELECT count(*) FROM raw_offer WHERE merchant_id IN (4,5) "
                "AND linked_status = 'linked' AND is_live").fetchone()[0]
            fiches = cur.execute(
                "SELECT count(DISTINCT product_id) FROM raw_offer "
                "WHERE merchant_id IN (4,5) AND linked_status = 'linked' "
                "AND is_live").fetchone()[0]
        print(f"\noffres rattachées après : {apres}  (+{apres - avant})")
        print(f"fiches concernées       : {fiches}")
        print(f"en {time.time() - t0:.0f}s")
        print("\n>>> lancer maintenant :  .venv\\Scripts\\mcpipe.exe freshness")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
