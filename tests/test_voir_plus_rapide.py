"""« Voir plus de produits » ne recalcule pas le panneau de filtres (19/10/2026) : les comptes
des filtres ne dependent ni de la page ni du tri, ils sont gardes par filtres seuls."""

import os

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="needs DATABASE_URL")


def test_les_pages_suivantes_et_les_tris_reutilisent_les_filtres(monkeypatch):
    from fastapi.testclient import TestClient

    from mcsite import cache, queries
    from mcsite.app import app

    appels = []
    original = queries.facets

    def espion(conn, f):
        appels.append(f)
        return original(conn, f)

    monkeypatch.setattr(queries, "facets", espion)
    with TestClient(app, follow_redirects=True) as c:
        cache.vider()
        assert c.get("/c/helmet").status_code == 200
        assert c.get("/c/helmet?page=2").status_code == 200
        assert c.get("/c/helmet?page=3").status_code == 200
        assert c.get("/c/helmet?tri=prix").status_code == 200
        assert c.get("/c/helmet?tri=prix&page=2").status_code == 200
    assert len(appels) == 1, f"le panneau de filtres a ete recalcule {len(appels)} fois"
