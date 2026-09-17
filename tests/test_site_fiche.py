"""Ce que la fiche produit déclare aux moteurs de recherche.

Ces données ne se voient pas à l'écran : c'est exactement pour ça qu'elles ont
besoin d'un test. Une fiche qui annoncerait une note de produit inventée, ou un
code-barres fabriqué par le pipeline, serait retirée des résultats enrichis — et
personne ne s'en apercevrait en regardant la page.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcsite.app import _donnees_structurees, _fil_structure


class _Url:
    scheme = "https"
    netloc = "motocomparo.com"


class _Requete:
    url = _Url()


def _produit(**extra: Any) -> dict[str, Any]:
    base = {
        "id": 1,
        "slug": "ixon-blanky-housse-bk-0497a262",
        "brand_code": "ixon",
        "colour_code": "bk",
        "model_display": "Housse moto Ixon BLANKY",
        "best_title": "",
        "category_code": "maintenance",
        "category_label": "Entretien",
        "image_url": None,
    }
    base.update(extra)
    return base


def _offre(prix: float | None, stock: bool | None = True) -> dict[str, Any]:
    return {"price": prix, "in_stock": stock}


def test_fourchette_sur_les_offres_achetables():
    """Le prix bas annoncé doit être un prix qu'on peut payer aujourd'hui."""
    rows = [_offre(43.50, stock=False), _offre(47.49), _offre(89.99)]
    d = _donnees_structurees(_Requete(), _produit(), rows, None, None)
    assert d["offers"]["lowPrice"] == "47.49"   # pas 43,50 : article en rupture
    assert d["offers"]["highPrice"] == "89.99"
    assert d["offers"]["offerCount"] == 3
    assert d["offers"]["availability"].endswith("InStock")


def test_tout_en_rupture_se_declare_en_rupture():
    rows = [_offre(43.50, stock=False), _offre(47.49, stock=False)]
    d = _donnees_structurees(_Requete(), _produit(), rows, None, None)
    assert d["offers"]["availability"].endswith("OutOfStock")
    # plus rien d'achetable : la fourchette repart des prix connus
    assert d["offers"]["lowPrice"] == "43.50"


def test_jamais_de_note_de_produit():
    """Les cinq étoiles de la fiche disent « comparateur indépendant ».

    Les déclarer comme une note ferait retirer le site des résultats enrichis.
    """
    d = _donnees_structurees(_Requete(), _produit(), [_offre(50.0)], None, None)
    assert "aggregateRating" not in d
    assert "review" not in d


def test_un_ean_est_declare_comme_ean():
    d = _donnees_structurees(
        _Requete(), _produit(), [_offre(50.0)], None, "3661615370291")
    assert d["gtin13"] == "3661615370291"
    assert "sku" not in d


def test_une_reference_qui_n_est_pas_un_ean_reste_une_reference():
    d = _donnees_structurees(_Requete(), _produit(), [_offre(50.0)], None, "AB-1234")
    assert d["sku"] == "AB-1234"
    assert "gtin13" not in d


def test_sans_prix_aucune_offre_n_est_declaree():
    d = _donnees_structurees(_Requete(), _produit(), [_offre(None)], None, None)
    assert "offers" not in d


@pytest.mark.parametrize("couleur", ["unknown", None, ""])
def test_couleur_inconnue_non_declaree(couleur):
    d = _donnees_structurees(
        _Requete(), _produit(colour_code=couleur), [_offre(50.0)], None, None)
    assert "color" not in d


def test_le_fil_suit_accueil_rayon_produit():
    f = _fil_structure(_Requete(), _produit())
    noms = [e["name"] for e in f["itemListElement"]]
    assert noms == ["Accueil", "Entretien", "Housse moto Ixon BLANKY"]
    assert [e["position"] for e in f["itemListElement"]] == [1, 2, 3]
    assert f["itemListElement"][1]["item"] == "https://motocomparo.com/c/maintenance"


def test_le_fil_saute_le_rayon_quand_il_n_y_en_a_pas():
    f = _fil_structure(_Requete(), _produit(category_code=None, category_label=None))
    assert [e["name"] for e in f["itemListElement"]] == [
        "Accueil", "Housse moto Ixon BLANKY"]
    assert [e["position"] for e in f["itemListElement"]] == [1, 2]
