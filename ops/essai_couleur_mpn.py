"""Le garde-fou de couleur de la passe préfixe : que change-t-il, exactement ?

`mcpipe verify` est passé de 7 à 177 incohérences après la passe préfixe du
2026-09-14. Mesuré : 171 portent sur des fiches où Maxxess/Moto-Axxe rencontre
un autre marchand, et 154 des 159 incohérences de couleur portent sur une fiche
contenant au moins une offre SANS couleur déclarée.

La cause : G3 compare l'offre entrante à UNE offre de la fiche et tolère qu'une
couleur soit absente d'un côté. Une offre rouge peut donc entrer par la porte
d'une offre sans couleur et atterrir sur une fiche par ailleurs noire. Le
garde-fou raisonne par paire là où la cohérence se juge sur l'ensemble.

Ce script mesure le correctif AVANT de le payer par un `match` : il rejoue la
passe avec et sans, dans une transaction annulée, et compte ce qu'on gagne
(incohérences évitées) contre ce qu'on perd (rattachements corrects écartés).

Rien n'est écrit.

    python ops/essai_couleur_mpn.py
"""

from __future__ import annotations

import os
import sys
import time

import psycopg
from dotenv import load_dotenv

RACINE = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(RACINE, "src"))
from mcpipe.match import _LINK_MPN_PREFIXE  # noqa: E402

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

# Le correctif se repère par sa première ligne : son corps a évolué (égalité
# stricte d'abord, puis inclusion de couleurs) et le figer ici aurait cassé le
# banc d'essai à chaque ajustement.
_DEBUT = "  -- G3bis : la couleur se juge sur la FICHE"
assert _DEBUT in _LINK_MPN_PREFIXE, "le garde-fou a changé de forme"
SANS = _LINK_MPN_PREFIXE[:_LINK_MPN_PREFIXE.index(_DEBUT)] + "\n"


def _mesure(cur, sql: str, nom: str) -> dict:
    """Repart d'un état propre : on défait les rattachements de la passe, on la
    rejoue, on compte. Tout est dans la transaction annulée par l'appelant."""
    cur.execute("""
        UPDATE raw_offer SET product_id = NULL, linked_status = 'unresolved',
               link_method = NULL, link_confidence = NULL
        WHERE link_method = 'mpn_prefixe'
    """)
    defaits = cur.rowcount
    t0 = time.time()
    cur.execute(sql)
    poses = cur.rowcount

    # Les incohérences de couleur créées par CETTE passe : une fiche touchée
    # dont les offres portent deux couleurs déclarées différentes.
    cur.execute("""
        SELECT count(*) FROM (
            SELECT o.product_id
            FROM raw_offer o JOIN offer_signature s ON s.raw_offer_id = o.id
            WHERE o.is_live AND o.product_id IN (
                    SELECT product_id FROM raw_offer WHERE link_method = 'mpn_prefixe')
              AND s.primary_colour IS NOT NULL
            GROUP BY o.product_id
            HAVING count(DISTINCT s.primary_colour) > 1) t
    """)
    incoherentes = cur.fetchone()[0]
    print(f"  {nom:<28} rattachements {poses:>6,}   fiches incoherentes {incoherentes:>5,}"
          .replace(",", " ") + f"   ({time.time() - t0:.0f}s, {defaits} defaits)")
    return {"poses": poses, "incoherentes": incoherentes}


def main() -> None:
    conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '900s'")
            avant = _mesure(cur, SANS, "sans le garde-fou")

            # L'échantillon se tire ICI, dans la passe sans garde-fou : c'est
            # la seule où les rattachements écartés existent encore. Le tirer
            # d'avance obligeait à retrouver la fiche par sous-requête
            # corrélée — neuf minutes pour douze lignes.
            cur.execute("""
                SELECT left(o.raw_title, 52), s.primary_colour, p.colour_code,
                       (SELECT left(b.raw_title, 52) FROM raw_offer b
                        WHERE b.product_id = o.product_id
                          AND b.merchant_id NOT IN (4, 5)
                        ORDER BY b.id LIMIT 1)
                FROM raw_offer o
                JOIN offer_signature s ON s.raw_offer_id = o.id
                JOIN product p ON p.id = o.product_id
                WHERE o.link_method = 'mpn_prefixe'
                  AND s.primary_colour IS NOT NULL
                  AND NOT (
                        string_to_array(split_part(s.primary_colour, '|', 1), '-')
                          <@ string_to_array(split_part(p.colour_code, '|', 1), '-')
                     OR string_to_array(split_part(p.colour_code, '|', 1), '-')
                          <@ string_to_array(split_part(s.primary_colour, '|', 1), '-'))
                ORDER BY random() LIMIT 14
            """)
            echantillon = cur.fetchall()
        conn.rollback()

        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '900s'")
            apres = _mesure(cur, _LINK_MPN_PREFIXE, "avec le garde-fou")

        print()
        print(f"  rattachements perdus : {avant['poses'] - apres['poses']:,}"
              .replace(",", " "))
        print(f"  fiches assainies     : "
              f"{avant['incoherentes'] - apres['incoherentes']:,}".replace(",", " "))

        print(chr(10) + "--- rattachements ECARTES par le garde-fou, a juger ---" + chr(10))
        for i, (titre, coul, fiche_coul, face) in enumerate(echantillon, 1):
            print(f"{i:>3}. offre {coul:<14} -> fiche {fiche_coul}")
            print(f"     {titre}")
            print(f"  vs {face}")
    finally:
        conn.rollback()
        conn.close()
        print(chr(10) + "(transaction annulee - rien n a ete ecrit)")


if __name__ == "__main__":
    main()
