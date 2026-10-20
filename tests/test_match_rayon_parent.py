"""« Casques » et ses sous-types (2 a 5) ne sont pas un conflit de rayon (19-20/10/2026).

« Casques » (1) et « Casques integraux » (2) decrivent le meme article ; deux enfants (2 et 3) ou deux rayons
sans lien (1 et 11, electronique) restent un conflit. On execute le fragment SQL tel qu'il est dans `match`.
"""

import pytest

from mcpipe import match as m
from mcpipe.db import connect

DEBUT = "    SELECT a.gtin\n    FROM (SELECT DISTINCT gtin, category_id FROM members WHERE category_id != 25) a"
FIN = "    WHERE NOT (a.category_id = 1 AND b.category_id IN (2, 3, 4, 5))\n"


def _fragment() -> str:
    sql = m._BUILD_GTIN_UNITS
    i = sql.index(DEBUT)
    return sql[i: sql.index(FIN, i) + len(FIN)]


def _rayons_en_conflit(lignes):
    try:
        conn = connect()
    except Exception as exc:  # pas de base locale
        pytest.skip(f"base indisponible : {exc}")
    with conn:
        conn.execute("CREATE TEMP TABLE members (gtin text, category_id smallint) ON COMMIT DROP")
        with conn.cursor().copy("COPY members FROM STDIN") as cp:
            for l in lignes:
                cp.write_row(l)
        rendu = sorted(r[0] for r in conn.execute(_fragment()))
        conn.rollback()
    return rendu


def test_parent_et_enfant_ne_sont_pas_un_conflit():
    assert _rayons_en_conflit([("g1", 1), ("g1", 2)]) == []


def test_deux_enfants_differents_sont_un_conflit():
    assert _rayons_en_conflit([("g1", 2), ("g1", 3)]) == ["g1"]


def test_parent_et_enfant_d_un_autre_parent_sont_un_conflit():
    # 1 = Casques ; 6 = Blousons (pas de lien) ; 11 est un rayon sans lien avec les casques
    assert _rayons_en_conflit([("g1", 1), ("g1", 6)]) == ["g1"]


def test_le_rayon_inconnu_25_ne_compte_pas_et_un_seul_rayon_non_plus():
    assert _rayons_en_conflit([("g1", 25), ("g1", 2), ("g2", 4), ("g2", 4)]) == []


def test_les_pieces_de_casque_et_les_protections_restent_des_rayons_distincts():
    # 30 = pieces et accessoires casque (enfant de 1) : une visiere n'est pas un casque
    assert _rayons_en_conflit([("g1", 1), ("g1", 30)]) == ["g1"]
    # 28 pilote / 29 moto sont enfants de 11 : on ne les confond pas non plus avec 11
    assert _rayons_en_conflit([("g1", 11), ("g1", 28)]) == ["g1"]
    assert _rayons_en_conflit([("g1", 28), ("g1", 29)]) == ["g1"]


def test_parent_enfant_et_un_deuxieme_enfant_reste_un_conflit():
    assert _rayons_en_conflit([("g1", 1), ("g1", 2), ("g1", 3)]) == ["g1"]


def test_l_ancienne_regle_du_nombre_de_rayons_distincts_a_disparu():
    assert "count(DISTINCT category_id) FILTER (WHERE category_id != 25) > 1" not in m._BUILD_GTIN_UNITS
