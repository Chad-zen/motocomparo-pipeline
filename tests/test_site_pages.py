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
    assert "data-ean" in r.text


def test_une_fiche_inconnue_est_un_404_pas_un_500(client):
    assert client.get("/p/ce-slug-n-existe-pas-du-tout").status_code == 404


def test_une_ancienne_fiche_est_un_410_pas_un_404(client):
    """Une adresse en forme de fiche (`…-4b6a63c0`) qui n'existe plus ne reviendra pas : 410, que
    Google retire plus vite de son index qu'un 404 (84 fiches mortes vues par Googlebot, 19-20/10)."""
    assert client.get("/p/ancienne-fiche-disparue-4b6a63c0").status_code == 410


def test_les_flux_de_l_ancien_site_sont_un_410(client):
    for chemin in ("/product/casque-i30-dexta-hjc/feed/", "/shop/casques/antivol-clip/feed/",
                   "/product-category/casques/feed/"):
        assert client.get(chemin, follow_redirects=False).status_code == 410, chemin


def test_le_sitemap_n_affirme_pas_une_date_de_modification_par_page(client):
    r = client.get("/sitemap-1.xml")
    assert r.status_code == 200 and "<loc>" in r.text and "<lastmod>" not in r.text


def test_l_ancien_parametre_de_graphique_renvoie_a_l_accueil(client):
    r = client.get("/?mc_ph_chart=184693", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/"


def test_l_accueil_ouvre_sur_le_budget_et_ses_images_existent(client):
    """L'accueil n'a plus d'affiche (retiree le 17/10/2026 : elle repoussait le
    curseur de budget sous la ligne de flottaison, 665 px sur mobile). Il garde
    un <h1> masque a l'oeil, et chaque image qu'il reference doit exister : un
    logo de marque ou un picto manquant ne leve aucune erreur, il s'affiche
    casse."""
    import re
    from pathlib import Path

    from mcsite import app as mod
    h = client.get("/").text
    assert "<h1" in h, "l'accueil n'a plus de titre de page"
    assert 'id="budget"' in h, "le curseur de budget a disparu de l'accueil"
    assert "affiche-portrait" not in h, "l'affiche est revenue sans qu'on l'ait decide"
    assert 'name="robots" content="noindex' not in h, "l'accueil est en noindex"
    images = re.findall(r'src="/static/((?:marques-logos|reassurance|logo_filigrane)[^"?]*)', h)
    assert images, "aucune image propre a l'accueil n'est referencee"
    for nom in images:
        assert (Path(mod.HERE) / "static" / nom).is_file(), nom


def test_les_images_de_l_accueil_declarent_leur_taille(client):
    """PageSpeed du 17/10/2026 : CLS 0,104 pour un seuil a 0,1, des images sans
    `width` ni `height` -- le navigateur ne reserve pas leur place et la page
    bouge quand elles arrivent. Les photos des marchands, les logos de marques
    et les logos marchands doivent tous declarer leur taille."""
    import re

    h = client.get("/").text
    balises = re.findall(r"<img\b[^>]*>", h)
    assert balises, "aucune image dans l'accueil"
    sans = [b for b in balises
            if ("marques-logos/" in b or "marchands/" in b or 'src="http' in b)
            and "width=" not in b]
    assert not sans, f"{len(sans)} image(s) sans largeur : {sans[:2]}"


def test_la_remise_d_une_carte_suit_la_formule_et_les_paliers_de_la_fiche():
    """Une carte qui annoncerait -30 % pendant que la fiche en dit -25 serait une
    promesse que la page suivante dement : meme formule, memes seuils."""
    from decimal import Decimal

    from mcsite.app import _remise_carte

    assert _remise_carte({"cheapest": Decimal("75"), "dearest": Decimal("100"), "merchant_count": 3}) \
        == {"pct": 25, "niveau": "orange"}
    assert _remise_carte({"cheapest": Decimal("50"), "dearest": Decimal("100"), "merchant_count": 2}) \
        == {"pct": 50, "niveau": "rouge"}
    assert _remise_carte({"cheapest": Decimal("90"), "dearest": Decimal("100"), "merchant_count": 2}) \
        == {"pct": 10, "niveau": "sobre"}
    # rien a annoncer : un seul marchand, pas d'ecart, ou un ecart qui s'arrondit a 0
    assert _remise_carte({"cheapest": Decimal("50"), "dearest": Decimal("100"), "merchant_count": 1}) is None
    assert _remise_carte({"cheapest": Decimal("80"), "dearest": Decimal("80"), "merchant_count": 2}) is None
    assert _remise_carte({"cheapest": Decimal("79"), "dearest": Decimal("79.2"), "merchant_count": 2}) is None
    assert _remise_carte({"cheapest": None, "dearest": None, "merchant_count": 2}) is None
    # plus de plafond (17/10/2026) : -59 % s'affiche
    assert _remise_carte({"cheapest": Decimal("53.99"), "dearest": Decimal("132.90"), "merchant_count": 3})         == {"pct": 59, "niveau": "rouge"}


def test_toutes_les_categories_garde_la_taille_et_la_marque(client):
    """17/10/2026 : « Toutes les categories » pointait vers `/produits` tout nu ;
    choisir une taille puis revenir a toutes les categories l'effacait."""
    import re

    h = client.get("/c/jacket?taille=M&marque=alpinestars").text
    m = re.search(r'facette__retour"\s*href="([^"]*)"', h)
    assert m, "le lien de retour a disparu"
    lien = m.group(1).replace("&amp;", "&")
    assert lien.startswith("/produits?"), lien
    assert "taille=M" in lien and "marque=alpinestars" in lien, lien


def test_la_courbe_de_budget_ignore_les_accessoires_du_rayon():
    """17/10/2026 : « un casque a moins de 27 euros, ca n'existe pas » -- la courbe
    comptait les visieres, ecrans et pare-soleil de `helmet.accessory`, enfant du rayon."""
    from mcsite.app import _ids_equipement

    rayon = {"ids": [1, 2, 3, 5, 30, 4],
             "enfants": [{"id": 2, "code": "helmet.integral"}, {"id": 30, "code": "helmet.accessory"},
                         {"id": 3, "code": "helmet.jet"}]}
    assert _ids_equipement(rayon) == [1, 2, 3, 5, 4]
    # un rayon sans enfants (gants, bottes) ne change pas
    assert _ids_equipement({"ids": [8], "enfants": []}) == [8]


def test_public_d_une_fiche_enfant_cross():
    from mcsite.queries import _public
    p = _public({"genre_age": "U-E", "best_title": "Gants moto cross enfant Troy Lee Designs GP Pro"})
    assert p["enfant"] is True and p["est_cross"] is True
    r = _public({"genre_age": "F-A", "best_title": "Gants Ixon RS4 AIR LADY - FEMME"})
    assert r["enfant"] is False and r["est_cross"] is False


def test_les_suggestions_visent_le_meme_public(client):
    """Un gant cross enfant ne proposait que des gants route femme et cross adulte (21/10/2026)."""
    from mcsite import queries
    from mcsite.app import pool
    with pool.connection() as conn:
        p = queries.product(conn, "troyleedesigns-designs-gants-gp-lee-pro-troy-bk-ef20504f")
        if p is None:
            pytest.skip("fiche absente de cette base")
        vues = queries.similaires(conn, p, 6) + queries.meme_gamme(conn, p, 8)
        for v in vues:
            autre = queries.product(conn, v["slug"])
            assert autre["genre_age"].endswith("-E"), v["slug"]


def test_les_boutons_voir_l_offre_passent_par_aller_et_ne_montrent_pas_le_lien_d_affiliation():
    """Le lien d'affiliation (track.effiliation.com…) ne doit plus etre dans la page (23/10/2026)."""
    import pathlib
    gabarit = pathlib.Path(__file__).parent.parent / "src/mcsite/templates/_fiche.html"
    texte = gabarit.read_text(encoding="utf-8")
    assert "deeplink" not in texte
    assert texte.count('href="/aller/') >= 3


def test_les_liens_des_codes_promo_passent_aussi_par_aller():
    import pathlib
    for nom in ("_fiche.html", "codes_promo.html"):
        texte = (pathlib.Path(__file__).parent.parent / "src/mcsite/templates" / nom).read_text(encoding="utf-8")
        assert 'href="{{ c.url }}"' not in texte


def test_remise_carte_un_pvc_remplace_l_ecart_entre_marchands(monkeypatch):
    """Prix public conseille connu : barre = PVC, pourcentage = ecart a ce PVC. Jamais les deux (23/10/2026)."""
    from decimal import Decimal

    from mcsite import app

    monkeypatch.setattr(app, "_pvc_de", lambda slug: 200.0 if slug == "avec-pvc" else None)
    it = {"slug": "avec-pvc", "cheapest": Decimal("150"), "dearest": Decimal("160"), "merchant_count": 3}
    assert app._remise_carte(it) == {"pct": 25, "niveau": "orange", "barre": 200.0, "pvc": True}
    # sous 3 % du PVC : rien, et SURTOUT pas l'ecart entre marchands (160 contre 150 ferait -6 %)
    assert app._remise_carte({**it, "cheapest": Decimal("197")}) is None
    # sans PVC : l'ancien ecart entre marchands, inchange
    assert app._remise_carte({**it, "slug": "sans-pvc"}) == {"pct": 6, "niveau": "sobre"}
