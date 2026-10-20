"""La page /codes-promo (20/10/2026) : seulement les codes en cours, chez des marchands affiches."""

import os

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="needs DATABASE_URL")


def test_la_page_ne_montre_que_les_codes_en_cours():
    from mcpipe.db import connect
    from mcsite import queries

    conn = connect()
    try:
        mid = conn.execute("SELECT id FROM merchant WHERE affiche ORDER BY id LIMIT 1").fetchone()[0]
        for code, deb, fin, retire in (
            ("TESTACTIF", "current_date - 1", "current_date + 10", "NULL"),
            ("TESTEXPIRE", "current_date - 30", "current_date - 1", "NULL"),
            ("TESTRETIRE", "current_date - 1", "current_date + 10", "now()"),
            ("TESTFUTUR", "current_date + 5", "current_date + 20", "NULL"),
        ):
            conn.execute(
                f"INSERT INTO code_promo (merchant_id, code, libelle, debut_le, fin_le, retire_le, source) "
                f"VALUES (%s, %s, 'essai', {deb}, {fin}, {retire}, 'manuel')", (mid, code))
        codes = {c["code"] for c in queries.codes_promo_actifs(conn)}
        assert "TESTACTIF" in codes
        assert not codes & {"TESTEXPIRE", "TESTRETIRE", "TESTFUTUR"}
    finally:
        conn.rollback()            # rien n'est garde
        conn.close()


def test_la_page_repond():
    from fastapi.testclient import TestClient

    from mcsite.app import app

    with TestClient(app) as c:
        r = c.get("/codes-promo")
    assert r.status_code == 200
    assert "Codes promo en cours" in r.text
    assert 'href="/codes-promo"' in r.text            # le lien du pied de page
