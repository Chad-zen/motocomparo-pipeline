"""Un code-barres tape dans la barre montre l'apercu de la fiche (19/10/2026) :
`/recherche` y sautait deja avec Entree, la liste deroulante ne montrait rien."""

import os

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="needs DATABASE_URL")


def test_fiche_par_gtin_est_la_meme_que_celle_d_entree():
    from mcpipe.db import connect
    from mcsite import queries

    conn = connect()
    try:
        row = conn.execute(
            "SELECT o.gtin FROM raw_offer o JOIN product p ON p.id = o.product_id "
            "JOIN product_stats s ON s.product_id = p.id "
            "WHERE o.gtin IS NOT NULL AND o.is_live AND p.status <> 'merged' "
            "AND s.cheapest IS NOT NULL LIMIT 1").fetchone()
        if not row:
            pytest.skip("aucun code-barres dans cette base")
        gtin = row[0]
        fiche = queries.fiche_par_gtin(conn, gtin)
        assert fiche is not None
        assert fiche["slug"] == queries.slug_par_gtin(conn, gtin)
        assert queries.fiche_par_gtin(conn, "00000000") is None
    finally:
        conn.close()


def test_l_api_montre_la_fiche_d_un_code_barres():
    from fastapi.testclient import TestClient
    from mcpipe.db import connect
    from mcsite import queries
    from mcsite.app import app

    conn = connect()
    try:
        row = conn.execute(
            "SELECT o.gtin FROM raw_offer o JOIN product p ON p.id = o.product_id "
            "JOIN product_stats s ON s.product_id = p.id "
            "WHERE o.gtin ~ '^[0-9]{13}$' AND o.is_live AND p.status <> 'merged' "
            "AND s.cheapest IS NOT NULL LIMIT 1").fetchone()
        if not row:
            pytest.skip("aucun EAN-13 dans cette base")
        slug = queries.fiche_par_gtin(conn, row[0])["slug"]
    finally:
        conn.close()
    with TestClient(app) as client:
        r = client.get("/api/suggestions", params={"q": row[0]})
    assert r.status_code == 200
    donnees = r.json()
    slugs = [p["slug"] for p in donnees.get("produits", []) + donnees.get("meilleurs", [])]
    assert slug in slugs


def test_un_code_barres_dit_de_quelle_taille_il_est():
    """4530935604074 est la taille S de l'Arai Quantic Frost : la liste doit le dire
    (19/10/2026), avec le prix de cette taille."""
    from mcpipe.db import connect
    from mcsite import queries

    conn = connect()
    try:
        row = conn.execute(
            "SELECT o.gtin, v.size_code FROM raw_offer o "
            "JOIN offer_variant_link l ON l.raw_offer_id = o.id "
            "JOIN variant v ON v.id = l.variant_id "
            "JOIN product p ON p.id = o.product_id "
            "JOIN product_stats s ON s.product_id = p.id "
            "WHERE o.gtin ~ '^[0-9]{13}$' AND o.is_live AND v.size_code NOT IN ('TU') "
            "AND p.status <> 'merged' AND s.cheapest IS NOT NULL LIMIT 1").fetchone()
        if not row:
            pytest.skip("aucun code-barres avec taille dans cette base")
        fiche = queries.fiche_par_gtin(conn, row[0])
    finally:
        conn.close()
    assert fiche["taille"] == row[1] or fiche["taille"]
    assert fiche["prix_taille"] is not None
