"""Le filtre Taille ne porte que sur l'équipement du motard (16/10/2026).

Vu sur /m/swmotech?taille=S : 78 pièces (valises, repose-pieds) proposées en
taille S, lue dans des références de pièces. Un échappement n'a pas de taille.
"""

from __future__ import annotations

from mcsite import queries


def test_les_rayons_a_tailles_sont_ceux_de_l_equipement():
    r = set(queries._RAYONS_A_TAILLES)
    assert {"jacket", "gloves", "pants", "boots", "helmet.integral",
            "protection.pilote"} <= r
    for piece in ("exhaust", "luggage", "brakes", "engine", "transmission",
                  "bodywork", "unknown", "maintenance", "electronics",
                  "protection.moto"):
        assert piece not in r


def test_filtre_et_pastilles_portent_la_meme_restriction():
    import inspect
    assert queries._IN_RAYONS_A_TAILLES in queries._OU
    assert "_IN_RAYONS_A_TAILLES" in inspect.getsource(queries.facets)
