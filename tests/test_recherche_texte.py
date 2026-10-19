"""La page de resultats entend la recherche comme les suggestions (19/10/2026) :
« szr blanc arai » donnait des fiches dans la liste deroulante et zero apres
Entree. `model_display` est trie par ordre alphabetique (« Evo R Sz Vas ») et la
couleur n'est dans aucun titre : il faut lire le titre marchand recolle et le
code couleur de la fiche."""

import os

import pytest

from mcsite import queries


def test_les_mots_de_couleur_deviennent_un_code():
    assert queries._couleurs_des_mots(["szr", "blanc", "arai"]) == ["", "WH", ""]
    assert queries._couleurs_des_mots(["blanche", "white", "noir"]) == ["WH", "WH", "BK"]
    assert queries._couleurs_des_mots(None) is None


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="needs DATABASE_URL")
def test_szr_blanc_arai_trouve_des_fiches():
    from mcpipe.db import connect

    conn = connect()
    try:
        _, n_blanc = queries.listing_filtre(
            conn, queries.Filtres(texte="szr blanc arai", marchands=2), 5, 0)
        _, n_sans = queries.listing_filtre(
            conn, queries.Filtres(texte="szr arai", marchands=2), 5, 0)
        _, n_absent = queries.listing_filtre(
            conn, queries.Filtres(texte="xyzzyplugh", marchands=2), 5, 0)
    finally:
        conn.close()
    if n_sans == 0:
        pytest.skip("pas d'Arai SZ-R dans cette base")
    assert 0 < n_blanc <= n_sans
    assert n_absent == 0
