"""Le controle 1 de validation (validation/01_ecarts_de_prix.py) sur trois fiches inventees."""

import importlib.util
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

_spec = importlib.util.spec_from_file_location(
    "controle_prix", Path(__file__).resolve().parents[1] / "validation" / "01_ecarts_de_prix.py")
controle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(controle)


def _offres():
    return pd.DataFrame({
        "product_id": [1, 1, 1, 1,    2, 2,     3],
        "price":      [4.05, 9.36, 8.60, 44.01, 100.0, 120.0, 50.0],
    })


def test_une_fiche_avec_une_offre_a_dix_fois_les_autres_est_signalee():
    r = controle.ecarts_de_prix(_offres(), seuil=5)
    assert list(r.index) == [1]
    assert round(r.loc[1, "rapport"], 1) == 10.9


def test_un_seuil_plus_bas_en_signale_davantage_pas_une_fiche_a_une_seule_offre():
    r = controle.ecarts_de_prix(_offres(), seuil=1.1)
    assert set(r.index) == {1, 2}            # la fiche 3 n'a qu'une offre : rien a comparer


def test_rien_a_signaler_donne_un_tableau_vide():
    assert controle.ecarts_de_prix(_offres(), seuil=50).empty
