"""Le filtre Marques : les marques cochees montent en tete, et on en coche
plusieurs depuis une page de marque (19/10/2026 : « nox » tape dans la barre
mene a /m/nox, ou la marque cochee restait enfouie dans la liste repliee et ou
on ne pouvait pas en ajouter une deuxieme)."""

import os
import re

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="needs DATABASE_URL")


def _lignes(html):
    bloc = html[html.index('data-facette="Marques"'):]
    bloc = bloc[:bloc.index("</details>")]
    return [(("est-actif" in m.group(1)),
             re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(3))).strip().split(" ")[0].lower(),
             m.group(2))
            for m in re.finditer(r'<a class="facette__ligne ([^"]*)"[^>]*?href="([^"]*)">(.*?)</a>',
                                 bloc, re.S)]


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from mcsite.app import app

    with TestClient(app, follow_redirects=True) as c:
        yield c


def _deux_marques():
    from mcpipe.db import connect

    conn = connect()
    try:
        rows = conn.execute(
            "SELECT p.brand_code FROM product p JOIN product_stats s ON s.product_id = p.id "
            "WHERE s.merchant_count >= 2 AND p.status <> 'merged' AND p.brand_code <> '' "
            "GROUP BY 1 ORDER BY count(*) DESC LIMIT 6").fetchall()
    finally:
        conn.close()
    if len(rows) < 6:
        pytest.skip("pas assez de marques dans cette base")
    return rows[4][0], rows[5][0]      # deux marques loin de la tete du classement


def test_les_marques_cochees_montent_en_tete(client):
    a, b = _deux_marques()
    lignes = _lignes(client.get(f"/produits?marque={a}&marque={b}").text)
    assert [x[0] for x in lignes[:2]] == [True, True]


def test_sur_une_page_de_marque_on_peut_en_cocher_une_deuxieme(client):
    a, b = _deux_marques()
    lignes = _lignes(client.get(f"/m/{a}").text)
    assert lignes[0][0] is True                           # la marque de la page est en tete, cochee
    non_cochee = next(x for x in lignes if not x[0])
    assert non_cochee[2].startswith("/produits?")         # on quitte la page de marque pour le listing
    assert non_cochee[2].count("marque=") == 2            # ... avec les DEUX marques
    assert lignes[0][2] in ("/produits?", "/produits")    # decocher la marque de la page : sans marque
