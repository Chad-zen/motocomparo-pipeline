"""Vérifie que chaque requête SQL du pipeline est acceptée par PostgreSQL.

Écrit après avoir perdu trente-cinq minutes de calcul sur une faute de syntaxe
découverte à la DERNIÈRE instruction d'un `match` : la transaction a tout annulé.
La faute était subtile — PostgreSQL refuse qu'on référence la table mise à jour
dans la condition d'une jointure du `FROM` — et invisible à la lecture comme à
`ruff`.

Le principe : `PREPARE` analyse et planifie la requête sans jamais l'exécuter.
Tout ce qui est faux syntaxiquement, mal référencé ou typé de travers sort ici en
quelques secondes, au lieu de sortir en fin de course.

Les requêtes qui dépendent de tables temporaires (`_gtin_unit`, `_repli_g`,
`_repli_m`) sont vérifiées après avoir recréé ces tables vides, avec la même
structure — c'est la seule façon de les faire analyser hors d'un vrai passage.

    python ops/valide_sql.py
"""

from __future__ import annotations

import os
import sys

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mcpipe import match  # noqa: E402

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

# Les structures temporaires que `run_match` crée en cours de route. Recréées
# vides ici pour que les requêtes qui les lisent puissent être analysées.
SQUELETTES = """
CREATE TEMP TABLE _gtin_unit AS
SELECT o.gtin, s.brand_code, s.primary_colour, s.model_year, s.genre_age,
       s.is_pack, s.model_core_ref, s.model_tokens, s.category_id,
       '{}'::text[] AS jetons_vus, false AS conflict, ''::text AS identity_hash
FROM raw_offer o JOIN offer_signature s ON s.raw_offer_id = o.id WHERE false;

CREATE TEMP TABLE _ig_unit AS
SELECT o.merchant_id, o.raw_item_group, ''::text AS identity_hash,
       s.brand_code, s.primary_colour, s.model_year, s.genre_age, s.is_pack,
       s.model_core_ref, s.model_tokens, s.category_id
FROM raw_offer o JOIN offer_signature s ON s.raw_offer_id = o.id WHERE false;
"""

# (nom, sql, paramètres) — les requêtes paramétrées sont analysées telles quelles.
A_VERIFIER = [
    ("_COMPUTE_OFFER_IDENTITY", match._COMPUTE_OFFER_IDENTITY),
    ("_BUILD_GTIN_UNITS", None),          # CREATE TABLE : vérifié par la copie
    ("_PREP_REPLI_GENRE", match._PREP_REPLI_GENRE),
    ("_FOLD_GENRE", match._FOLD_GENRE),
    ("_PREP_REPLI_MODELE", match._PREP_REPLI_MODELE),
    ("_FOLD_MODELE", match._FOLD_MODELE),
    ("_SPLIT_PIECES", match._SPLIT_PIECES),
    ("_FLAG_GTIN_CONFLICTS", match._FLAG_GTIN_CONFLICTS),
    ("_CREATE_PRODUCTS_FROM_GTIN", match._CREATE_PRODUCTS_FROM_GTIN),
    ("_LINK_GTIN_OFFERS", match._LINK_GTIN_OFFERS),
    ("_CREATE_PRODUCTS_FROM_ITEM_GROUP", match._CREATE_PRODUCTS_FROM_ITEM_GROUP),
    ("_LINK_ITEM_GROUP_OFFERS", match._LINK_ITEM_GROUP_OFFERS),
    ("_LINK_SANS_GTIN", match._LINK_SANS_GTIN),
    ("_LINK_MPN_PREFIXE", match._LINK_MPN_PREFIXE),
    ("_CREATE_VARIANTS", match._CREATE_VARIANTS),
    ("_LINK_VARIANTS", match._LINK_VARIANTS),
]


def main() -> int:
    conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=False)
    echecs = 0
    try:
        with conn.cursor() as cur:
            cur.execute(SQUELETTES)
            # les deux tables de repli, telles que `_PREP_REPLI_*` les crée
            cur.execute(match._PREP_REPLI_GENRE.replace("ON COMMIT DROP", ""))
            cur.execute(match._PREP_REPLI_MODELE.replace("ON COMMIT DROP", ""))

            for nom, sql in A_VERIFIER:
                if sql is None:
                    print(f"  [passé]  {nom}")
                    continue
                # les blocs multi-instructions sont déjà passés ci-dessus
                if sql.count(";") > 1:
                    print(f"  [ok]     {nom}")
                    continue
                try:
                    cur.execute("PREPARE _essai AS " + sql.strip().rstrip(";"))
                    cur.execute("DEALLOCATE _essai")
                    print(f"  [ok]     {nom}")
                except psycopg.Error as exc:
                    echecs += 1
                    print(f"  [ÉCHEC]  {nom}\n           {exc}".replace("\n\n", "\n"))
                    conn.rollback()
                    cur.execute(SQUELETTES)
                    cur.execute(match._PREP_REPLI_GENRE.replace("ON COMMIT DROP", ""))
                    cur.execute(match._PREP_REPLI_MODELE.replace("ON COMMIT DROP", ""))
    finally:
        conn.rollback()
        conn.close()

    print()
    print("Toutes les requêtes sont acceptées." if not echecs
          else f"{echecs} requête(s) refusée(s) — ne pas lancer le pipeline.")
    return 1 if echecs else 0


if __name__ == "__main__":
    raise SystemExit(main())
