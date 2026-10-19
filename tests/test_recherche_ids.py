"""La recherche par mots calcule une fois les fiches trouvees (index trigramme) au lieu de
reevaluer la clause texte sur chaque fiche, dans chacune des dizaines de requetes d'une page
(19/10/2026 : 33 a 39 s sur « shoei neotec gt »). Meme resultat qu'avant, 5 a 50 fois plus vite."""

import os

import pytest

from mcsite import queries

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="needs DATABASE_URL")


def test_les_mots_assez_longs_sont_separes_des_mots_courts():
    assert queries._f_recherche("SZ-R") == "szr"            # 3 lettres : un trigramme existe
    assert queries._f_recherche("GT") == "gt"                # 2 lettres : pas de trigramme
    assert len(queries._f_recherche("Intégral")) == 8


def test_les_jokers_tapes_ne_sont_pas_des_jokers():
    e = queries._echapper_like("a%b_c")
    assert e == "a" + chr(92) + "%b" + chr(92) + "_c"


@pytest.mark.parametrize("texte", ["hjc rpha", "gants hiver", "sz-r", "noir", "xyzzy"])
def test_meme_resultat_avec_et_sans_les_ids_precalcules(texte, monkeypatch):
    from mcpipe.db import connect
    from mcsite import cache

    conn = connect()
    try:
        conn.execute("SET statement_timeout = '300s'")
        f = queries.Filtres(texte=texte, marchands=2)
        cache.vider()
        neuf, n_neuf = queries.listing_filtre(conn, f, 60, 0)
        original = queries._args
        monkeypatch.setattr(queries, "_args", lambda f, conn=None: original(f, None))
        vieux, n_vieux = queries.listing_filtre(conn, f, 60, 0)
    finally:
        conn.close()
    assert n_neuf == n_vieux
    assert {x["slug"] for x in neuf} == {x["slug"] for x in vieux}
