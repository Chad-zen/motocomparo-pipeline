"""Chaque page rend-elle ?

LA LEÇON QUI A COÛTÉ LE PLUS CHER, ÉCRITE LE 17/09/2026. Les 239 vérifications
d'alors sont passées au vert alors que l'accueil rendait une erreur 500 :
`'statique_existe' is undefined`, une fonction appelée par le gabarit et jamais
déclarée. Aucun test ne RENDAIT une page — ils examinaient des requêtes, des
règles, des fichiers, tout sauf le résultat.

Le même jour, la mise en production a échoué pour une raison de la même famille :
une vue recréée par le mauvais rôle, et toutes les pages en 500. Deux pannes
totales en une journée, aucune attrapée, parce qu'il manquait le test le plus
bête : ouvrir la page.

Ces vérifications ne jugent pas ce qu'une page raconte — d'autres fichiers s'en
chargent. Elles vérifient qu'elle EXISTE. C'est peu, et c'est ce qui manquait.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="rendre une page demande la base")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from mcsite.app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def une_fiche(client):
    """Le slug d'une vraie fiche, pris dans l'accueil : en écrire un en dur
    ferait passer le test au vert le jour où le pipeline le renomme."""
    import re
    m = re.search(r'href="/p/([^"]+)"', client.get("/").text)
    if not m:
        pytest.skip("aucune fiche sur l'accueil")
    return m.group(1)


@pytest.mark.parametrize("chemin", [
    "/",
    "/produits",
    "/produits?tri=nouveautes",
    "/produits?tri=prix&page=2",
    "/c/helmet",
    "/c/helmet?tri=nouveautes",
    "/c/helmet?couleur=BK",
    "/recherche?q=arai",
    "/recherche?q=",
    "/recherche?q=sz-r",
    "/bons-plans",
    "/marques",
    "/infos",
    "/api/suggestions?q=arai",
    "/robots.txt",
    "/sitemap.xml",
])
def test_la_page_rend(client, chemin):
    r = client.get(chemin)
    assert r.status_code == 200, f"{chemin} -> {r.status_code}"


def test_la_fiche_produit_rend(client, une_fiche):
    r = client.get(f"/p/{une_fiche}")
    assert r.status_code == 200
    assert "Réf." in r.text


def test_une_fiche_inconnue_est_un_404_pas_un_500(client):
    assert client.get("/p/ce-slug-n-existe-pas-du-tout").status_code == 404


def test_l_affiche_est_toujours_servie(client):
    """Un `<source>` retenu mais introuvable n'affiche pas l'image de repli : il
    n'affiche rien. L'affiche disparaîtrait de l'accueil sans qu'aucune erreur
    ne soit levée — c'est pourquoi la présence du fichier est vérifiée ici, et
    pas seulement celle de la balise."""
    import re
    from pathlib import Path

    from mcsite import app as mod
    h = client.get("/").text
    sources = re.findall(r'srcset="/static/([^"?]+)', h) + \
              re.findall(r'<img src="/static/(affiche[^"?]+)', h)
    assert sources, "aucune affiche dans l'accueil"
    for nom in sources:
        assert (Path(mod.HERE) / "static" / nom).is_file(), nom
