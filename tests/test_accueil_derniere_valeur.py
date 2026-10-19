"""Un bloc de l'accueil qui devient trop lent garde sa derniere valeur correcte
au lieu de disparaitre (19/10/2026 : « Ca a baisse cette semaine » avait
disparu pendant un match en production, sur un seul coeur)."""

import psycopg
import pytest

from mcsite import app


@pytest.fixture(autouse=True)
def _propre(monkeypatch):
    app._DERNIERE_BONNE.clear()
    app._ECHEC_ACCUEIL.clear()
    # le cache de bloc est contourne : on teste la reaction a l'echec, pas la duree
    monkeypatch.setattr(app.cache, "au_chaud", lambda cle, fabrique, ttl=None: fabrique())
    yield
    app._DERNIERE_BONNE.clear()
    app._ECHEC_ACCUEIL.clear()


def _trop_lent():
    raise psycopg.errors.QueryCanceled("trop lent")


def test_un_bloc_trop_lent_garde_sa_derniere_valeur():
    assert app._section_accueil("b", lambda: ["baisse A"], []) == ["baisse A"]
    assert app._section_accueil("b", _trop_lent, []) == ["baisse A"]


def test_sans_valeur_connue_le_bloc_reste_vide():
    assert app._section_accueil("b2", _trop_lent, []) == []


def test_apres_un_echec_le_calcul_n_est_pas_relance_a_chaque_visite():
    appels = []

    def fab():
        appels.append(1)
        _trop_lent()

    app._section_accueil("b3", fab, [])
    app._section_accueil("b3", fab, [])
    app._section_accueil("b3", fab, [])
    assert len(appels) == 1


def test_la_pause_passee_le_calcul_reprend():
    app._section_accueil("b4", _trop_lent, [])
    app._ECHEC_ACCUEIL["b4"] = 0.0
    assert app._section_accueil("b4", lambda: ["revenu"], []) == ["revenu"]
