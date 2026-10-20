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


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="needs DATABASE_URL")
def test_les_animations_sont_progressives():
    """Les animations ne doivent rien retirer a qui n'a pas JavaScript ou a demande moins de mouvement :
    le contenu est dans le HTML avec ses chiffres definitifs, et `reveal` n'est pose que par le script."""
    import re

    from fastapi.testclient import TestClient

    from mcsite.app import app

    with TestClient(app, follow_redirects=True) as c:
        h = c.get("/infos").text
        js = c.get("/static/apropos.js")
    assert js.status_code == 200
    assert 'src="/static/apropos.js' in h
    assert 'class="reveal' not in h                              # jamais cache par le HTML
    assert re.search(r'data-compte="\d+"[^>]*>plus de ', h)       # le chiffre definitif est deja la
    assert "prefers-reduced-motion" in js.text                    # le script respecte « moins d'animation »


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="needs DATABASE_URL")
def test_la_page_ne_tombe_pas_si_les_chiffres_sont_trop_lents(monkeypatch):
    """Apres un redemarrage, les comptages a froid peuvent depasser le delai de 15 s : la page garde sa
    presentation et omet seulement les tuiles chiffrees, au lieu de repondre 500."""
    import psycopg
    from fastapi.testclient import TestClient

    from mcsite import app as mod

    reel = mod.cache.au_chaud

    def coupe_les_chiffres(cle, fabrique, ttl=None):
        if cle == "apropos-chiffres":
            raise psycopg.errors.QueryCanceled("trop lent")
        return reel(cle, fabrique, ttl=ttl)

    monkeypatch.setattr(mod.cache, "au_chaud", coupe_les_chiffres)
    with TestClient(mod.app, follow_redirects=True) as c:
        r = c.get("/infos")
    assert r.status_code == 200
    assert "apropos__chiffres" not in r.text               # pas de tuiles sans chiffres
    assert 'id="engagements' in r.text and 'id="cgu"' in r.text
    assert "chez 7 marchands" in r.text or "chez 8 marchands" in r.text or " marchands," in r.text
