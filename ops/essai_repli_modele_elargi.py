"""Que se passerait-il si le repli de modèle ne demandait plus de référence ?

`_PREP_REPLI_MODELE` est restreint aux unités portant un `model_core_ref`. La
restriction était prudente et documentée : sans elle, le seau (marque, rayon,
couleur, année, genre) contient aussi les titres génériques — « Ermax Bulle
Haute » et sa famille — où élire le titre le plus long risquait de grossir la
méga-fusion connue au lieu de la réduire.

Elle a un coût, constaté le 2026-09-14 sur deux fiches Arai SZ-R VAS EVO : cinq
tailles du même casque, quatre sur une fiche, la cinquième seule sur une autre
parce qu'un marchand qui ne vend QUE cette taille écrit un titre plus court. Les
deux unités n'ont pas de référence modèle, donc la règle ne les voit jamais.

Ce script compare les deux règles côte à côte, dans une transaction annulée, et
sort ce qu'il faut pour JUGER plutôt que pour se rassurer :

  - ce que la règle élargie ajoute, et rien d'autre ;
  - la taille du plus gros groupe fusionné — c'est là que se cacherait une
    méga-fusion, pas dans la moyenne ;
  - un échantillon des nouvelles fusions, à relire une par une.

Rien n'est écrit : ni `product`, ni `raw_offer`, ni `offer_signature`. La table
de travail `essai_unites` doit exister (`python ops/essai_replis.py`).

    python ops/essai_repli_modele_elargi.py          # 25 exemples
    python ops/essai_repli_modele_elargi.py 60       # 60 exemples
"""

from __future__ import annotations

import os
import sys
import time

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mcpipe.match import (  # noqa: E402
    _FOLD_GENRE,
    _FOLD_MODELE,
    _PREP_REPLI_GENRE,
    _PREP_REPLI_MODELE,
)

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

SANS_ON_COMMIT = {"ON COMMIT DROP": ""}

# La seule différence entre les deux règles : la restriction est levée.
RESTRICTION = "AND model_core_ref IS NOT NULL"
assert RESTRICTION in _PREP_REPLI_MODELE, "la restriction a changé de forme"

COPIE = """
CREATE TEMP TABLE _gtin_unit AS SELECT * FROM essai_unites;
CREATE INDEX ON _gtin_unit (gtin);
CREATE INDEX ON _gtin_unit (identity_hash);
ANALYZE _gtin_unit;
CREATE TEMP TABLE _avant AS
  SELECT gtin, identity_hash, model_tokens FROM _gtin_unit;
CREATE INDEX ON _avant (gtin);
ANALYZE _avant;
"""


def _prep(elargi: bool) -> str:
    sql = _PREP_REPLI_MODELE.replace("ON COMMIT DROP", "")
    return sql.replace(RESTRICTION, "") if elargi else sql


def passe(cur, elargi: bool) -> dict:
    """Applique genre puis modèle, et rend ce que la passe a déplacé."""
    cur.execute(COPIE)
    cur.execute(_PREP_REPLI_GENRE.replace("ON COMMIT DROP", ""))
    cur.execute(_FOLD_GENRE)
    cur.execute(_prep(elargi))
    cur.execute(_FOLD_MODELE)
    deplacees = cur.rowcount

    cur.execute("""
        SELECT count(*), count(DISTINCT a.identity_hash),
               (SELECT count(*) FROM raw_offer o
                JOIN _gtin_unit u2 ON u2.gtin = o.gtin
                JOIN _avant a2 ON a2.gtin = u2.gtin
                WHERE u2.identity_hash <> a2.identity_hash AND o.is_live)
        FROM _gtin_unit u JOIN _avant a USING (gtin)
        WHERE u.identity_hash <> a.identity_hash
    """)
    n, fiches, offres = cur.fetchone()

    # Le plus gros groupe d'arrivée : une méga-fusion se voit ici, jamais dans
    # une moyenne. On compte les unités qui se retrouvent sur un même hash.
    cur.execute("""
        SELECT max(n), avg(n)::numeric(6,2) FROM (
          SELECT count(*) AS n FROM _gtin_unit GROUP BY identity_hash) t
    """)
    pire, moyenne = cur.fetchone()
    return {"deplacees": deplacees, "unites": n, "fiches": fiches,
            "offres": offres, "pire_groupe": pire, "groupe_moyen": moyenne}


def main() -> None:
    combien = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=False)
    t0 = time.time()
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '900s'")
            if cur.execute("SELECT to_regclass('essai_unites')").fetchone()[0] is None:
                print("table de travail absente — lancer d'abord :"
                      "  python ops/essai_replis.py")
                return

            print("règle ACTUELLE (référence modèle exigée) ...", flush=True)
            actuelle = passe(cur, elargi=False)
            for k, v in actuelle.items():
                print(f"    {k:<14} {v}")
        conn.rollback()

        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '900s'")
            print("\nrègle ÉLARGIE (restriction levée) ...", flush=True)
            elargie = passe(cur, elargi=True)
            for k, v in elargie.items():
                print(f"    {k:<14} {v}")

            print("\n  ÉCART")
            for k in ("unites", "fiches", "offres", "pire_groupe"):
                print(f"    {k:<14} {actuelle[k]} -> {elargie[k]}"
                      f"   ({elargie[k] - actuelle[k]:+})")

            # On rejoue la règle actuelle dans une table à part pour isoler ce
            # que l'élargissement AJOUTE. Comparer deux exécutions complètes
            # mélangerait les fusions communes aux nouvelles.
            cur.execute("CREATE TEMP TABLE _nouv AS SELECT u.gtin, a.model_tokens AS avant,"
                        " u.model_tokens AS apres FROM _gtin_unit u JOIN _avant a USING (gtin)"
                        " WHERE u.model_tokens <> a.model_tokens"
                        "   AND NOT EXISTS (SELECT 1 FROM essai_unites e"
                        "     WHERE e.gtin = u.gtin"
                        "       AND e.model_core_ref IS NOT NULL)")
            n_nouv = cur.execute("SELECT count(*) FROM _nouv").fetchone()[0]
            print(f"\n  fusions AJOUTÉES par l'élargissement : {n_nouv:,}".replace(",", " "))

            print(f"\n--- {combien} fusions ajoutées, tirées au hasard, à juger ---\n",
                  flush=True)
            cur.execute("""
                SELECT array_to_string(n.avant,' '), array_to_string(n.apres,' '),
                       (SELECT left(o.raw_title,58) FROM raw_offer o
                        WHERE o.gtin = n.gtin ORDER BY o.id LIMIT 1)
                FROM _nouv n ORDER BY random() LIMIT %s
            """, (combien,))
            for i, (court, long_, titre) in enumerate(cur.fetchall(), 1):
                ajoutes = sorted(set((long_ or "").split()) - set((court or "").split()))
                print(f"{i:>3}. + {' '.join(ajoutes)[:20]:<20} | {(court or '')[:30]:<30}")
                print(f"     {titre}")
    finally:
        conn.rollback()
        conn.close()
        print(f"\n(transaction annulée — rien n'a été écrit) {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
