"""Les codes-barres d'une fiche multi-tailles — voir `_donnees_structurees`.

Un EAN par taille : la fiche ne doit jamais déclarer celui d'une seule taille
comme l'identifiant du produit entier.
"""

from types import SimpleNamespace

from mcsite.app import _donnees_structurees

_REQ = SimpleNamespace(url=SimpleNamespace(scheme="https", netloc="motocomparo.com"))
_P = {"slug": "arai-frost", "brand_code": "arai", "best_title": "Arai Frost",
      "model_display": "Frost", "colour_code": "unknown"}


def _offre(ean, taille, prix, stock=True):
    return {"ean": ean, "gtin": ean, "taille": taille, "price": prix,
            "in_stock": stock, "merchant": "fcmoto"}


def test_plusieurs_tailles_donnent_un_productgroup():
    rows = [_offre("4530935604074", "S", 637.46), _offre("4530935604074", "", 599.96),
            _offre("4530935604081", "M", 567.34)]
    codes = [{"ean": "4530935604074", "taille": "S"},
             {"ean": "4530935604081", "taille": "M"}]
    d = _donnees_structurees(_REQ, _P, rows, None, None, codes)
    assert d["@type"] == "ProductGroup"
    assert "gtin13" not in d
    par_taille = {v["size"]: v for v in d["hasVariant"]}
    assert par_taille["S"]["gtin13"] == "4530935604074"
    assert par_taille["S"]["offers"]["lowPrice"] == "599.96"
    assert par_taille["M"]["offers"]["offerCount"] == 1


def test_un_seul_ean_reste_un_product():
    rows = [_offre("4530935604074", "S", 637.46)]
    d = _donnees_structurees(_REQ, _P, rows, None, "4530935604074",
                             [{"ean": "4530935604074", "taille": "S"}])
    assert d["@type"] == "Product"
    assert d["gtin13"] == "4530935604074"
