"""Les facettes Matiere / Homologation / Saison comptent les fiches du filtre D'ABORD, puis leurs
valeurs (19/10/2026) : meme resultat que la jointure directe, 9 s -> 0,4 s sur les bottes noires."""

import os

import pytest

from mcsite import cache, queries

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="needs DATABASE_URL")

_ANCIENNE = """
    WITH carac AS MATERIALIZED ({carac})
    SELECT carac.valeur, count(*) AS n
    FROM product p JOIN product_stats s ON s.product_id = p.id
    LEFT JOIN carac ON carac.product_id = p.id
    {ou}
    GROUP BY 1
"""


@pytest.mark.parametrize("kw", [
    {"couleur": "BK", "rayon": "boots"},
    {"marque": ["shoei"], "rayon": "helmet"},
    {"genre": "femme", "rayon": "jacket"},
    {"texte": "hjc rpha"},
])
def test_les_facettes_de_caracteristiques_comptent_comme_avant(kw):
    from mcpipe.db import connect

    kw = dict(kw)
    conn = connect()
    try:
        conn.execute("SET statement_timeout = '300s'")
        rayon = kw.pop("rayon", None)
        if rayon:
            kw["categories"] = queries.find_category(queries.categories(conn), rayon)["ids"]
        f = queries.Filtres(marchands=2, **kw)
        cache.vider()
        facettes = queries.facets(conn, f)
        args = queries._args(f, conn)
        for param in queries.FILTRES_CARACTERISTIQUES:
            ancienne = {r["valeur"]: r["n"] for r in queries._rows(
                conn, _ANCIENNE.format(carac=queries._CARAC_SQL[param], ou=queries._OU), args)}
            vues = {x["valeur"]: x["n"] for x in facettes.get(param, [])}
            # la facette n'affiche que les valeurs lues : on compare ces lignes-la
            assert vues == {v: n for v, n in ancienne.items() if v is not None and v in vues}
    finally:
        conn.close()
