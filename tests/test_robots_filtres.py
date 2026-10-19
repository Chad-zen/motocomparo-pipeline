"""Les filtres sont fermes aux robots qu'ils soient le premier parametre ou un
suivant : `/*?taille=` ne couvre pas `/c/helmet?page=2&taille=L` (19/10/2026)."""

from fastapi.testclient import TestClient

from mcsite.app import app


def test_robots_ferme_les_filtres_en_premier_et_en_deuxieme_parametre():
    texte = TestClient(app).get("/robots.txt").text
    for filtre in ("marque", "prix_min", "prix_max", "taille", "couleur"):
        assert f"Disallow: /*?{filtre}=" in texte
        assert f"Disallow: /*&{filtre}=" in texte


def test_robots_garde_la_pagination_et_les_anciennes_adresses_ouvertes():
    texte = TestClient(app).get("/robots.txt").text
    assert "Disallow: /*?page=" not in texte
    assert "Disallow: /*&page=" not in texte
    assert "Allow: /product/*?taille=" in texte
