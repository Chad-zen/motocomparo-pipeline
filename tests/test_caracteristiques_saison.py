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
