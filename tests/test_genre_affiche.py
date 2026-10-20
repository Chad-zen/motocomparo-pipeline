"""Le genre du produit (Homme / Femme / Enfant) s'affiche sur les cartes et sur la fiche
(19/10/2026). Il existait dans la base (product.genre_age) mais n'etait qu'un filtre."""

import os
import re

import pytest

from mcsite import labels


def test_le_genre_n_est_affiche_que_quand_il_est_connu():
    assert labels.genre_age("H-A") == "Homme"
    assert labels.genre_age("F-A") == "Femme"
    assert labels.genre_age("H-E") == labels.genre_age("U-E") == "Enfant"
    # U = inconnu OU mixte : le pipeline ne les distingue pas, on n'affiche rien
    assert labels.genre_age("U-A") == ""
    assert labels.genre_age(None) == "" and labels.genre_age("") == "" and labels.genre_age("x") == ""


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="needs DATABASE_URL")
def test_les_cartes_et_la_fiche_montrent_le_genre():
    from fastapi.testclient import TestClient

    from mcsite.app import app

    with TestClient(app, follow_redirects=True) as c:
        liste = c.get("/c/jacket").text
        genres = re.findall(r'class="carte__genre">([^<]+)', liste)
        assert genres and set(genres) <= {"Homme", "Femme", "Enfant"}
        slug = re.search(r'href="/p/([^"]+)"[^>]*>(?:(?!</a>).)*?class="carte__genre"', liste, re.S).group(1)
        assert re.search(r"Pour : <strong>(Homme|Femme|Enfant)</strong>", c.get(f"/p/{slug}").text)
