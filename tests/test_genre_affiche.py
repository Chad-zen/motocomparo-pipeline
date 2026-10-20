"""Le genre du produit s'affiche sur la FICHE, selon le rayon (20/10/2026).

Pas sur les cartes de liste ; pas homme / femme pour les casques (le genre y vient du titre ou du
flux marchand et se trompe : un casque Klim d'expedition marque « Femme »). Le filtre par genre
des listes n'est pas touche."""

import os
import re

import pytest

from mcsite import labels


def test_le_genre_n_est_affiche_que_quand_il_est_connu():
    assert labels.genre_age("H-A") == "Homme"
    assert labels.genre_age("F-A") == "Femme"
    assert labels.genre_age("H-E") == labels.genre_age("U-E") == "Enfant"
    assert labels.genre_age("U-A") == ""                      # inconnu OU mixte : rien
    assert labels.genre_age(None) == "" and labels.genre_age("") == "" and labels.genre_age("x") == ""


def test_equipement_du_motard_homme_femme_enfant():
    for rayon in ("jacket", "pants", "gloves", "boots", "suit", "apparel_casual", "jersey", "protection.pilote"):
        assert labels.genre_fiche("F-A", rayon) == "Femme"
        assert labels.genre_fiche("H-A", rayon) == "Homme"
        assert labels.genre_fiche("U-E", rayon) == "Enfant"


def test_casques_jamais_homme_ni_femme():
    for rayon in ("helmet", "helmet.integral", "helmet.jet", "helmet.modular", "helmet.cross", "helmet.accessory"):
        assert labels.genre_fiche("F-A", rayon) == ""
        assert labels.genre_fiche("H-A", rayon) == ""
        assert labels.genre_fiche("U-A", rayon) == ""
        assert labels.genre_fiche("H-E", rayon) == "Enfant"   # l'age seulement, quand il est dit


def test_autres_rayons_rien():
    for rayon in ("protection", "protection.moto", "goggles", "exhaust", "battery", "", None):
        assert labels.genre_fiche("F-A", rayon) == ""


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="needs DATABASE_URL")
def test_les_cartes_n_affichent_pas_le_genre_mais_la_fiche_oui():
    from fastapi.testclient import TestClient

    from mcsite.app import app

    with TestClient(app, follow_redirects=True) as c:
        liste = c.get("/c/jacket").text
        assert "carte__genre" not in liste
        casques = c.get("/c/helmet").text
        assert "carte__genre" not in casques
        slug_casque = re.search(r'href="/p/([^"]+)"', casques).group(1)
        page = c.get(f"/p/{slug_casque}").text
        assert not re.search(r"Pour : <strong>(Homme|Femme)</strong>", page)
