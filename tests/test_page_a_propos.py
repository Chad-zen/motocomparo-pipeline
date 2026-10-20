"""La page « A propos » (20/10/2026) : une vraie presentation avant le juridique, avec des chiffres lus
en base et les ancres que le reste du site utilise (#donnees, #cgu, #mentions, #contact)."""

import os

import pytest

from mcsite.app import _arrondi_bas


def test_les_chiffres_sont_arrondis_vers_le_bas():
    assert _arrondi_bas(64891).startswith("plus de 64")
    assert _arrondi_bas(898883).startswith("plus de 890")
    assert _arrondi_bas(7) == "7"
    # toujours vrai le lendemain : jamais arrondi vers le haut
    for n in (1500, 64891, 898883, 123456):
        valeur = int("".join(c for c in _arrondi_bas(n) if c.isdigit()))
        assert valeur <= n


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="needs DATABASE_URL")
def test_la_page_presente_le_site_puis_garde_le_juridique():
    from fastapi.testclient import TestClient

    from mcsite.app import app

    with TestClient(app, follow_redirects=True) as c:
        h = c.get("/infos").text
    for ancre in ("engagements", "comment", "liens", "marchands", "donnees", "cgu", "mentions", "contact"):
        assert f'id="{ancre}' in h, ancre                      # les ancres existent
    assert h.index('id="engagements') < h.index('id="donnees"') < h.index('id="cgu"')   # presentation d'abord
    assert "marchands comparés" in h and "produits comparés" in h
    assert "Tous sont français" not in h                       # faux depuis Motoin (Allemagne)
    assert "Conditions générales d'utilisation" in h
