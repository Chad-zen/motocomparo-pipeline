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
SELECT o.merchant_id, o.raw_item_group, ''::text AS identity_hash, ''::text AS hash_base,
       s.brand_code, s.primary_colour, s.model_year, s.genre_age, s.is_pack,
       s.model_core_ref, s.model_tokens, s.category_id,
       0::bigint AS n, 0::numeric AS prix
FROM raw_offer o JOIN offer_signature s ON s.raw_offer_id = o.id WHERE false;

CREATE TEMP TABLE _hash_avant_decoupes AS
SELECT ''::text AS gtin, ''::text AS identity_hash WHERE false;

CREATE TEMP TABLE _ig_ref AS
SELECT ''::text AS h, ''::text AS t, 0::bigint AS m, ''::text AS g, 0::numeric AS prix WHERE false;

CREATE TABLE IF NOT EXISTS offre_detachee_prix (
    raw_offer_id bigint PRIMARY KEY, ancien_product_id bigint, ancien_link_method text,
    ancienne_confiance numeric, prix numeric, mediane_autres numeric,
    detache_le timestamptz NOT NULL DEFAULT now()
);
"""

# (nom, sql, paramètres) — les requêtes paramétrées sont analysées telles quelles.
A_VERIFIER = [
    ("_COMPUTE_OFFER_IDENTITY", match._COMPUTE_OFFER_IDENTITY),
    ("_ECARTER_DESACCORDS", match.sql_ecarter_desaccords([7])),
    ("_ECARTER_CONFLITS_NEUFS", match.sql_ecarter_conflits_neufs([7])),
    ("_BUILD_GTIN_UNITS", None),          # CREATE TABLE : vérifié par la copie
    ("_PREP_REPLI_GENRE", match._PREP_REPLI_GENRE),
    ("_FOLD_GENRE", match._FOLD_GENRE),
    ("_PREP_REPLI_MODELE", match._PREP_REPLI_MODELE),
    ("_FOLD_MODELE", match._FOLD_MODELE),
    ("_SPLIT_PIECES", match._SPLIT_PIECES),
    ("_SPLIT_PRIX", match._SPLIT_PRIX),
    ("_SPLIT_PRIX_HABILLEMENT", match._SPLIT_PRIX_HABILLEMENT),
    ("_BUILD_ITEM_GROUP_UNITS", None),    # CREATE TABLE AS : verifie par la copie
    ("_IG_REF", None),                    # CREATE TABLE AS
    ("_IG_SEPARER_PRIX", match._IG_SEPARER_PRIX),
    ("_DETACHER_CANDIDATS", match._DETACHER_CANDIDATS),
    ("_RATTACHER_LOG", None),             # CREATE TABLE IF NOT EXISTS : execute avec les squelettes
    ("_RATTACHER_CIBLES", None),          # CREATE TABLE AS : execute avec les squelettes
    ("_RATTACHER_RETENUES", None),        # CREATE TABLE AS : execute avec les squelettes
    ("_RATTACHER_COMPTER", match._RATTACHER_COMPTER),
    ("_DIAG_RAISONS", match._DIAG_RAISONS),
    ("_DIAG_DESACCORDS", match._DIAG_DESACCORDS),
    ("_RATTACHER_JOURNAL", match._RATTACHER_JOURNAL),
    ("_RATTACHER_APPLIQUER", match._RATTACHER_APPLIQUER),
    ("_FLAG_GTIN_CONFLICTS", match._FLAG_GTIN_CONFLICTS),
    ("_CREATE_PRODUCTS_FROM_GTIN", match._CREATE_PRODUCTS_FROM_GTIN),
    ("_LINK_GTIN_OFFERS", match._LINK_GTIN_OFFERS),
    ("_CREATE_PRODUCTS_FROM_ITEM_GROUP", match._CREATE_PRODUCTS_FROM_ITEM_GROUP),
    ("_LINK_ITEM_GROUP_OFFERS", match._LINK_ITEM_GROUP_OFFERS),
    ("_LINK_SANS_GTIN", match._LINK_SANS_GTIN),
    ("_LINK_MPN_PREFIXE", match._LINK_MPN_PREFIXE),
    ("_CREATE_VARIANTS", match._CREATE_VARIANTS),
    ("_ELAGUER_VARIANTES", match._ELAGUER_VARIANTES),
    ("_LINK_VARIANTS", match._LINK_VARIANTS),
]


def _tables_du_rattachement(cur) -> None:
    """Les trois CREATE du passage « rattacher a la fiche existante » : PREPARE ne sait pas
    analyser un CREATE TABLE AS, on les EXECUTE donc sur les squelettes vides (instantane), ce
    qui les valide et cree `_cibles` / `_rattache` pour les requetes qui les lisent."""
    for sql in (match._RATTACHER_LOG,
                match._RATTACHER_CIBLES.replace("ON COMMIT DROP", ""),
                match._RATTACHER_RETENUES.replace("ON COMMIT DROP", "")):
        cur.execute(sql)


def main() -> int:
    conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=False)
    echecs = 0
    try:
        with conn.cursor() as cur:
            cur.execute(SQUELETTES)
            # les deux tables de repli, telles que `_PREP_REPLI_*` les crée
            cur.execute(match._PREP_REPLI_GENRE.replace("ON COMMIT DROP", ""))
            cur.execute(match._PREP_REPLI_MODELE.replace("ON COMMIT DROP", ""))
            _tables_du_rattachement(cur)

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
                    _tables_du_rattachement(cur)
    finally:
        conn.rollback()
        conn.close()

    print()
    print("Toutes les requêtes sont acceptées." if not echecs
          else f"{echecs} requête(s) refusée(s) — ne pas lancer le pipeline.")
    return 1 if echecs else 0


if __name__ == "__main__":
    raise SystemExit(main())
