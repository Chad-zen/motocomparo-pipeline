"""Essai à blanc des deux replis d'identité, sans toucher au catalogue.

Les replis ne se mesurent pas après coup : `_BUILD_GTIN_UNITS` ne regarde que
les offres `unresolved`, et après un `match` réussi il n'y en a plus. On
reconstruit donc les mêmes unités en levant ce seul filtre — ce que verrait un
`match --reset`.

La construction coûte une vingtaine de minutes, et il faut pouvoir réessayer
une règle sans la repayer : elle est donc écrite une fois dans une table de
travail, `essai_unites`, que ce script crée et qui n'entre dans aucune vue ni
aucune requête du site. Les replis travaillent sur une COPIE temporaire et
n'écrivent jamais dans `product`, `raw_offer` ni `offer_signature`.

    python ops/essai_replis.py            # réutilise la table si elle existe
    python ops/essai_replis.py --refaire  # reconstruit les unités
    python ops/essai_replis.py --nettoyer # supprime la table de travail
"""

from __future__ import annotations

import os
import sys

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mcpipe.match import (  # noqa: E402
    _BUILD_GTIN_UNITS,
    _FOLD_GENRE,
    _FOLD_MODELE,
    _PREP_REPLI_GENRE,
    _PREP_REPLI_MODELE,
)

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

# le seul changement au SQL du pipeline : on ne se limite pas aux offres non
# résolues, puisqu'après un match il n'en reste aucune.
CONSTRUCTION = (
    _BUILD_GTIN_UNITS
    .replace("AND o.linked_status = 'unresolved'", "AND o.linked_status <> 'quarantined'")
    .replace("CREATE TEMP TABLE _gtin_unit ON COMMIT DROP AS", "CREATE TABLE essai_unites AS")
)

# les replis lisent `_gtin_unit` : la copie de travail porte donc ce nom.
COPIE = """
CREATE TEMP TABLE _gtin_unit AS SELECT * FROM essai_unites;
CREATE INDEX ON _gtin_unit (gtin);
ANALYZE _gtin_unit;
"""


def construire(cur) -> None:
    print("construction des unités (une vingtaine de minutes) ...", flush=True)
    cur.execute("DROP TABLE IF EXISTS essai_unites")
    cur.execute(CONSTRUCTION)
    cur.execute("CREATE INDEX ON essai_unites (gtin)")
    cur.execute("ANALYZE essai_unites")


def main() -> None:
    conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    try:
        with conn.cursor() as cur:
            if "--nettoyer" in sys.argv:
                cur.execute("DROP TABLE IF EXISTS essai_unites")
                print("table de travail supprimée.")
                return

            cur.execute("SELECT to_regclass('essai_unites') IS NOT NULL")
            existe = cur.fetchone()[0]
            if "--refaire" in sys.argv or not existe:
                construire(cur)

            cur.execute("SELECT count(*), count(*) FILTER (WHERE conflict) FROM essai_unites")
            total, conflits = cur.fetchone()
            print(f"  {total:,} unités  ({conflits:,} en conflit)".replace(",", " "),
                  flush=True)

        # à partir d'ici tout est temporaire, et rien n'est validé
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(COPIE)
            cur.execute("CREATE TEMP TABLE _avant AS SELECT gtin, identity_hash,"
                        " genre_age, model_tokens FROM _gtin_unit")
            cur.execute("CREATE INDEX ON _avant (gtin)")
            cur.execute("ANALYZE _avant")

            print("\nrepli 1 — le genre inconnu absorbé par le genre déclaré", flush=True)
            cur.execute(_PREP_REPLI_GENRE.replace("ON COMMIT DROP", ""))
            cur.execute(_FOLD_GENRE)
            print(f"  {cur.rowcount:,} unité(s) absorbée(s)".replace(",", " "), flush=True)

            print("\nrepli 2 — le mot en plus est déjà écrit chez la fiche courte", flush=True)
            cur.execute(_PREP_REPLI_MODELE.replace("ON COMMIT DROP", ""))
            cur.execute(_FOLD_MODELE)
            print(f"  {cur.rowcount:,} unité(s) absorbée(s)".replace(",", " "), flush=True)

            cur.execute("""
                SELECT count(*),
                       count(DISTINCT a.identity_hash),
                       (SELECT count(*) FROM raw_offer o
                        JOIN _gtin_unit u2 ON u2.gtin = o.gtin
                        JOIN _avant a2 ON a2.gtin = u2.gtin
                        WHERE u2.identity_hash <> a2.identity_hash AND o.is_live)
                FROM _gtin_unit u JOIN _avant a USING (gtin)
                WHERE u.identity_hash <> a.identity_hash
            """)
            deplacees, fiches, offres = cur.fetchone()
            print(f"\n  unités déplacées         : {deplacees:,}".replace(",", " "))
            print(f"  fiches qui disparaissent : {fiches:,}".replace(",", " "))
            print(f"  offres re-rassemblées    : {offres:,}".replace(",", " "), flush=True)

            print("\n--- 20 replis de genre, au hasard ---", flush=True)
            cur.execute("""
                SELECT a.genre_age, u.genre_age, array_to_string(u.model_tokens, ' '),
                       (SELECT left(o.raw_title, 60) FROM raw_offer o
                        WHERE o.gtin = u.gtin LIMIT 1)
                FROM _gtin_unit u JOIN _avant a USING (gtin)
                WHERE u.genre_age <> a.genre_age
                ORDER BY random() LIMIT 20
            """)
            for avant, apres, jetons, titre in cur.fetchall():
                print(f"  {avant} -> {apres}  [{(jetons or '')[:34]:<34}]  {titre}")

            print("\n--- 25 replis de modèle, au hasard ---", flush=True)
            cur.execute("""
                SELECT array_to_string(a.model_tokens, ' '),
                       array_to_string(u.model_tokens, ' '),
                       (SELECT left(o.raw_title, 56) FROM raw_offer o
                        WHERE o.gtin = u.gtin LIMIT 1)
                FROM _gtin_unit u JOIN _avant a USING (gtin)
                WHERE u.model_tokens <> a.model_tokens
                ORDER BY random() LIMIT 25
            """)
            for court, long, titre in cur.fetchall():
                ajoutes = sorted(set((long or "").split()) - set((court or "").split()))
                print(f"  + {' '.join(ajoutes)[:22]:<22} | {(court or '')[:32]:<32} | {titre}")
    finally:
        if not conn.autocommit:
            conn.rollback()
        conn.close()
        print("\n(replis annulés — seule `essai_unites` subsiste, hors du site)")


if __name__ == "__main__":
    main()
