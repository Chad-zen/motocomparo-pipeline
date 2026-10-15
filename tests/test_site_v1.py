"""Les anciennes adresses (v1) mènent quelque part, et jamais à une fiche douteuse.

Cas tirés des demandes réelles de Googlebot (journaux nginx du 15/10/2026).
"""

from __future__ import annotations

import os

import pytest

from mcsite import v1

MARQUES = {"hjc", "bardahl", "scorpion", "quadlock", "oneal", "visiodry", "shad", "ixon"}
LISTEES = {"hjc", "scorpion", "shad", "ixon"}


def test_les_accents_casses_de_la_v1_sont_rendus():
    assert v1.phrase("/product/a%C2%89cran-iridium-bleu-hj-32-pour-casque-hjc-f70/").startswith("ecran iridium")


def test_une_marque_n_est_reconnue_qu_en_toutes_lettres():
    # « vis » n'est pas Visiodry, « 100 » n'est pas 100%
    assert v1.marque_ecrite("vis tendeur de chaine".split(), MARQUES | {"100"}) is None
    assert v1.marque_ecrite("ecrou m32 100 mm".split(), MARQUES | {"100"}) is None
    assert v1.marque_ecrite("adaptateur universel quad lock".split(), MARQUES) == "quadlock"
    assert v1.marque_ecrite("ecran solaire o neal d srs".split(), MARQUES) == "oneal"


def test_le_premier_mot_de_produit_decide_du_rayon():
    assert v1.rayon_des_mots("ecran fume pour casque scorpion".split()) == "electronics"
    assert v1.rayon_des_mots("casque modulable hjc f100".split()) == "helmet.modular"
    assert v1.rayon_des_mots("kit chaine did".split()) == "transmission"
    assert v1.rayon_des_mots("plaquettes de frein".split()) == "brakes"
    assert v1.rayon_des_mots("bidule inconnu".split()) is None


def test_la_reference_de_modele_doit_etre_la_meme():
    # vu en production : « casque modulable hjc f100 gris » trouvait un i91
    candidates = lambda marque, texte: [  # noqa: E731
        ("hjc-i91-gy-db5127be", 0.71, "Casque modulable HJC i91 gris"),
        ("hjc-f100-gy-aaa", 0.66, "Casque modulable HJC F100 Gris Nardo")]
    assert v1.cible_fiche_v1("/product/casque-modulable-hjc-f100-gris-nardo-m/",
                             MARQUES, LISTEES, candidates) == "/p/hjc-f100-gy-aaa"
    seul_i91 = lambda marque, texte: candidates(marque, texte)[:1]  # noqa: E731
    assert v1.cible_fiche_v1("/product/casque-modulable-hjc-f100-gris-nardo-m/",
                             MARQUES, LISTEES, seul_i91) == "/m/hjc"
    # la référence peut être coupée par la ponctuation du titre marchand
    ixon = lambda marque, texte: [("ixon-u04-bk", 0.67, "Airbag moto Ixon IX-AIRBAG U04")]  # noqa: E731
    assert v1.cible_fiche_v1("/product/airbag-ix-airbag-u04-ixon/",
                             MARQUES, LISTEES, ixon) == "/p/ixon-u04-bk"


def test_une_fiche_n_est_visee_que_si_la_ressemblance_est_forte():
    forte = lambda marque, texte: [("bardahl-nettoyant-carburateur-500ml-abc", 0.72,  # noqa: E731
                                    "Nettoyant carburateur Bardahl 500ML")]
    faible = lambda marque, texte: [("scorpion-ecran-exo-210-air-def", 0.43,  # noqa: E731
                                     "Ecran casque Scorpion Exo FUME - EXO-210 AIR")]
    assert v1.cible_fiche_v1("/product/additif-bardahl-nettoyant-carburateur-500-ml/",
                             MARQUES, LISTEES, forte) == "/p/bardahl-nettoyant-carburateur-500ml-abc"
    # ressemblance faible : la page de la marque, pas un modèle voisin
    assert v1.cible_fiche_v1("/product/a%C2%89cran-scorpion-exo-s1-fuma/",
                             MARQUES, LISTEES, faible) == "/m/scorpion"
    # marque sans page : le rayon du premier mot de produit
    assert v1.cible_fiche_v1("/product/casque-jet-visiodry-x/",
                             MARQUES, LISTEES, faible) == "/c/helmet.jet"
    # rien de lisible : le catalogue
    assert v1.cible_fiche_v1("/product/25-trucs/", MARQUES, LISTEES, faible) == "/produits"


def test_anciennes_categories_et_boutique():
    assert v1.cible_rayon_v1("casques/") == "/c/helmet"
    assert v1.cible_rayon_v1("casques/integral/page/3/") == "/c/helmet.integral"
    assert v1.cible_rayon_v1("inconnue/") == "/produits"
    assert v1.cible_boutique_v1({"mc_type": "bagage", "mc_brand": "Shad"}, LISTEES) == "/c/luggage?marque=shad"
    assert v1.cible_boutique_v1({"mc_brand": "Shad"}, LISTEES) == "/m/shad"
    assert v1.cible_boutique_v1({"max_price": "100"}, LISTEES) == "/produits"


@pytest.fixture(scope="module")
def client():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("les routes demandent la base")
    from fastapi.testclient import TestClient

    from mcsite.app import app
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("ancienne, cible", [
    ("/product-category/gants/", "/c/gloves"),
    ("/shop/?mc_type=echap", "/c/exhaust"),
    ("/2026/08/05/rouler-en-securite-les-reflexes-qui-sauvent-2/", "/guides"),
    ("/about-us/", "/infos"),
    ("/sitemap_index.xml", "/sitemap.xml"),
])
def test_les_anciennes_adresses_sont_redirigees_pour_de_bon(client, ancienne, cible):
    r = client.get(ancienne, follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == cible


def test_une_ancienne_fiche_redirige_vers_une_page_qui_existe(client):
    r = client.get("/product/casque-modulable-hjc-f100-gris-nardo-m/", follow_redirects=False)
    assert r.status_code == 301
    assert client.get(r.headers["location"]).status_code == 200


@pytest.mark.parametrize("ancienne", ["/wp-cron.php", "/xmlrpc.php", "/wp-json/wp/v2/users",
                                      "/feed/", "/my-account/lost-password/"])
def test_la_mecanique_wordpress_est_declaree_disparue(client, ancienne):
    assert client.get(ancienne, follow_redirects=False).status_code == 410
