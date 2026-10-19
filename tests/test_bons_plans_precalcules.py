"""Les bons plans precalcules (19/10/2026) : la page lit 48 lignes rangees la nuit au
lieu de parcourir 640 000 offres (30 s sur le serveur)."""

import os

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="needs DATABASE_URL")


def test_la_lecture_rend_les_memes_bons_plans_que_le_calcul():
    from mcpipe.db import connect
    from mcsite import queries

    conn = connect()
    try:
        calcul = queries.bons_plans_calculer(conn, 12)
        n = queries.precalculer_bons_plans(conn, 12)
        lu = queries.bons_plans(conn, 12)
    finally:
        conn.close()
    assert n == len(calcul) == len(lu)
    assert [x["slug"] for x in lu] == [x["slug"] for x in calcul]
    assert [float(x["remise"]) for x in lu] == [float(x["remise"]) for x in calcul]


def test_sans_table_precalculee_la_page_calcule_comme_avant():
    from mcpipe.db import connect
    from mcsite import queries

    conn = connect()
    try:
        # DROP est transactionnel : la lecture echoue, `bons_plans` termine la transaction
        # (la table revient) puis calcule a la demande
        conn.execute("DROP TABLE IF EXISTS bons_plans_precalcules")
        lu = queries.bons_plans(conn, 3)
    finally:
        conn.close()
    assert len(lu) <= 3
