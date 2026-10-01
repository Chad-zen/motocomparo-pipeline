"""La Bécanerie vend aussi du vélo : ces lignes n'entrent jamais dans raw_offer.

Repris le 01/10/2026, à la réintégration du flux après deux semaines figé —
voir le commentaire de `_LABECANERIE_HORS_MOTO` dans normalize.py pour les
chiffres qui justifient la liste.
"""

from mcpipe.normalize import hors_perimetre


def test_les_categories_velo_sont_ecartees():
    for categorie in (
        "Partie cycle vélo", "Roue et pneu vélo", "Équipement cycliste",
        "Freinage vélo", "Accessoire vélo", "Casque vélo", "Bagagerie vélo",
        "Transport vélo", "Mobilité", "Nutrition et Bien-être",
    ):
        assert hors_perimetre("labecanerie", categorie)


def test_les_categories_moto_restent():
    # « Partie cycle » (sans le mot vélo) est la partie-cycle MOTO — fourche,
    # guidon, amortisseur. Le garder était tout l'enjeu de la liste.
    for categorie in (
        "Partie cycle", "Équipement route", "Carénage", "Freinage",
        "Moteur", "Équipement Cross", "Casque intégral", "Sportswear",
    ):
        assert not hors_perimetre("labecanerie", categorie)


def test_espaces_et_casse_ne_contournent_pas_le_filtre():
    assert hors_perimetre("labecanerie", "  Partie cycle vélo  ")


def test_valeur_absente_ne_fait_pas_planter():
    assert not hors_perimetre("labecanerie", None)
    assert not hors_perimetre("labecanerie", "")


def test_les_autres_marchands_ne_sont_pas_filtres():
    # Aucun autre marchand n'a cette liste : un casque "Équipement cycliste"
    # chez un marchand sans vélo resterait donc affiché, ce qui est voulu —
    # le filtre est spécifique au flux dont la contamination a été mesurée.
    assert not hors_perimetre("speedway", "Équipement cycliste")
    assert not hors_perimetre("motoblouz", "Partie cycle vélo")
