"""La recherche qui désigne une marque ou un rayon y mène directement.

« shoei » + Entrée coûtait 9,3 s à froid (16/10/2026) pour montrer moins
bien ce que /m/shoei montre déjà. Avec la base : voir la fixture `client`.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="module")
def client():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("le site a besoin de la base")
    from fastapi.testclient import TestClient

    from mcsite.app import app
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("q, cible", [
    ("shoei", "/m/shoei"),
    ("shoie", "/m/shoei"),                    # faute de frappe rattrapée
    ("gant hiver", "/c/gloves?saison=hiver"),
    ("casque integral", "/c/helmet.integral"),
    ("alpinestars gants", "/c/gloves?marque=alpinestars"),
])
def test_une_marque_ou_un_rayon_menent_a_leur_page(client, q, cible):
    r = client.get("/recherche", params={"q": q}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == cible


@pytest.mark.parametrize("q", ["arai sz-r", "casque bluetooth"])
def test_un_modele_garde_la_page_de_resultats(client, q):
    assert client.get("/recherche", params={"q": q}, follow_redirects=False).status_code == 200


def test_un_filtre_pose_dans_le_panneau_n_est_pas_perdu(client):
    r = client.get("/recherche", params={"q": "shoei", "tri": "prix"}, follow_redirects=False)
    assert r.status_code == 200
