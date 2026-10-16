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
    # un gant chauffant ou « Froid et pluie » est un gant d'hiver par sa fonction
    ("Gants Moto Chauffants", "hiver"),
    ("Froid et Pluie", "hiver"),
    # une saison écrite l'emporte sur la fonction
    ("Gants Moto Été chauffants", "ete"),
])
def test_la_saison_ecrite_dans_la_categorie_est_lue(categorie, attendu):
    assert saison(categorie) == attendu


@pytest.mark.parametrize("categorie", [
    "Gants Motocross", "Cross / TT / Enduro > Gants Cross", "gloves",
    "Gants Moto Femme", "Sous-gants et sur-gants",
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


# --- l'homologation écrite « Homologation CE » et l'obligation des casques ------

def test_homologation_ce_forme_nominale_est_lue_sur_les_gants_et_les_bottes():
    """« Homologation CE. » (Maxxess, Moto-Axxe) n'était pas reconnue : 49 gants."""
    from mcpipe.caracteristiques import botte, gant
    assert gant.lire("Gants", "Gants hiver. Homologation CE. Membrane étanche.").homologation == "CE"
    assert gant.lire("Gants", "Paume renforcée. Marquage CE niveau 2").homologation == "CE"
    assert botte.lire("Bottes", "Bottes route. Homologation CE. Semelle.").homologation == "CE"


def test_un_niveau_de_confort_n_est_pas_une_homologation():
    from mcpipe.caracteristiques import botte, gant
    assert gant.lire("Gants", "Un haut niveau de protection et de confort.").homologation is None
    assert gant.lire("Gants", "Coque au niveau des phalanges.").homologation is None
    assert botte.lire("Bottes", "Un haut niveau de confort.").homologation is None


def test_la_version_ece_non_precisee_ne_prete_pas_de_norme():
    from mcpipe import caracteristiques as c
    from mcsite import queries
    assert c._HOMOLOGATION_CASQUE_NON_PRECISEE == "version non précisée"
    # la requête de filtre range tout ce qui n'est pas 22.05 / 22.06 sous « ece »
    assert "'22[.]0[56]$'" in queries._CARAC_SQL["homologation"].replace("^", "")  \
        or "22[.]0[56]" in queries._CARAC_SQL["homologation"]
    assert queries._LIBELLES_FILTRE["homologation"]["ece"] == "ECE, version non précisée"
    assert queries._SOURCE_PRIORITE["obligation"] > queries._SOURCE_PRIORITE["flux"]
