"""La saison écrite par le marchand dans sa propre catégorie (16/10/2026)."""

from __future__ import annotations

import pytest

from mcpipe.caracteristiques import saison_de_la_categorie as saison


@pytest.mark.parametrize("categorie, attendu", [
    ("Gants Moto Hiver", "hiver"),
    ("Gants Moto Été", "ete"),
    ("Gants Moto Mi-saison", "mi-saison"),
    ("Equipement du motard > Gants moto > Gants moto hiver", "hiver"),
    ("Equipement du motard > Gants moto > Gants moto mi-saison", "mi-saison"),
    ("Équipement route > Vêtement hiver > Sous gant", "hiver"),
    ("Gants moto ete", "ete"),
])
def test_la_saison_ecrite_dans_la_categorie_est_lue(categorie, attendu):
    assert saison(categorie) == attendu


@pytest.mark.parametrize("categorie", [
    "Gants Motocross", "Gants Moto Chauffants", "gloves", "Gants Moto Femme",
    "Pneu hivernal", "Blouson cadette", "", None,
])
def test_une_categorie_muette_ne_donne_rien(categorie):
    assert saison(categorie) is None


def test_la_source_categorie_passe_apres_le_flux():
    from mcsite import queries
    p = queries._SOURCE_PRIORITE
    assert p["flux"] < p["categorie"]


# --- la matière déclarée dans une colonne du flux ------------------------------

from mcpipe.caracteristiques import (_MATIERE_BLOUSON, _MATIERE_CALOTTE,
                                     _MATIERE_TEXTILE_CUIR, matiere_declaree)


def test_la_matiere_d_un_gant_vient_de_la_colonne_du_marchand():
    assert matiere_declaree("Textile", _MATIERE_TEXTILE_CUIR) == "textile"
    assert matiere_declaree("Cuir", _MATIERE_TEXTILE_CUIR) == "cuir"
    assert matiere_declaree("Cuir|Textile", _MATIERE_TEXTILE_CUIR) == "cuir et textile"
    assert matiere_declaree(" cuir ", _MATIERE_TEXTILE_CUIR) == "cuir"


def test_un_blouson_et_un_casque_ont_leur_propre_vocabulaire():
    assert matiere_declaree("Cuir|Textile", _MATIERE_BLOUSON) == "cuir-textile"
    assert matiere_declaree("Carbone|Fibre de verre", _MATIERE_CALOTTE) == "composite"
    assert matiere_declaree("Fibre de verre", _MATIERE_CALOTTE) == "fibre"


@pytest.mark.parametrize("valeur", ["Aluminium", "Acier chrome-vanadium", "Plastique", "", None])
def test_une_valeur_hors_vocabulaire_est_ecartee(valeur):
    for vocab in (_MATIERE_TEXTILE_CUIR, _MATIERE_BLOUSON, _MATIERE_CALOTTE):
        assert matiere_declaree(valeur, vocab) is None
