"""Les tailles achetables, rangees la nuit dans une table (20/10/2026) : une page filtree par taille
la lit au lieu de reverifier chaque fiche dans chacune de ses dix requetes. Meme resultat que le
calcul a la demande, 3 a 4 fois plus vite ; sans table, ou si elle est perimee, on revient au calcul."""

import os

import pytest

from mcsite import cache, queries

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="needs DATABASE_URL")


@pytest.fixture()
def conn():
    from mcpipe.db import connect

    c = connect()
    c.execute("SET statement_timeout = '300s'")
    yield c
    queries._OU = queries._OU_LIVE         # l'etat global ne doit pas deborder sur les autres tests
    c.close()


def test_les_deux_clauses_ne_different_que_par_la_taille():
    assert queries._OU_TABLE != queries._OU_LIVE
    assert queries._OU_TABLE.replace(queries._TAILLE_TABLE, queries._TAILLE_LIVE) == queries._OU_LIVE


@pytest.mark.parametrize("kw", [
    {"rayon": "gloves", "taille": ["L"], "prix_max": 80},
    {"rayon": "boots", "taille": ["EU42"]},
    {"rayon": "jacket", "taille": ["XL", "2XL"], "couleur": "BK"},
])
def test_meme_resultat_avec_la_table_et_sans(conn, kw):
    kw = dict(kw)
    kw["categories"] = queries.find_category(queries.categories(conn), kw.pop("rayon"))["ids"]
    f = queries.Filtres(marchands=2, **kw)
    queries.precalculer_tailles_achetables(conn)
    res = {}
    for mode, clause in (("live", queries._OU_LIVE), ("table", queries._OU_TABLE)):
        queries._OU = clause
        cache.vider()
        items, total = queries.listing_filtre(conn, f, 60, 0)
        facettes = queries.facets(conn, f)
        res[mode] = (total, [x["slug"] for x in items],
                     [(x["valeur"], x["n"]) for x in facettes["marques"]],
                     [(x["valeur"], x["n"]) for x in facettes["tailles"]])
    assert res["live"] == res["table"]


def test_sans_table_ou_table_perimee_on_revient_au_calcul(conn):
    queries.precalculer_tailles_achetables(conn)
    assert queries.verifier_table_tailles(conn) is True and queries._OU is queries._OU_TABLE
    conn.execute("UPDATE taille_achetable SET calcule_le = now() - interval '3 days'")
    conn.commit()
    assert queries.verifier_table_tailles(conn) is False and queries._OU is queries._OU_LIVE
    conn.execute("DROP TABLE taille_achetable")
    conn.commit()
    assert queries.verifier_table_tailles(conn) is False and queries._OU is queries._OU_LIVE
    queries.precalculer_tailles_achetables(conn)        # on laisse la table en place, fraiche
