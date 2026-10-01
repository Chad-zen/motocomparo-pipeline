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


# Le filet de sécurité par titre : des outils et consommables d'atelier
# (démonte-pneu, dégraissant, support mural…) partagent une catégorie
# générique avec la moto et échappent au filtre par catégorie.

def test_le_titre_ecarte_les_outils_de_velo_en_categorie_partagee():
    for titre in (
        "Démonte pneu vélo Michelin jaune nylon (lot de 3 pièces)",
        "Dégraissant vélo WD-40 (500ml)",
        "Support présentoir vélo au plafond à poulie par cadre(1 vélo)",
        "Kit Tubeless 27.5'' WAG pour VTT (30mm)",
        "Trottinette Disney Cars pliable et réglable rouge",
        "Draisienne Kiddimoto Heroes Evel Knievel",
        "Batterie Vélo Électrique Shimano BT-E8016 pour Support Central 630 W",
    ):
        assert hors_perimetre("labecanerie", "Partie cycle", titre)


def test_le_titre_epargne_le_cyclomoteur_et_le_nom_propre():
    # « vélomoteur » (un cyclomoteur, donc motorisé) et « VéloSolex » (un nom
    # propre) ne sont pas le vélo qu'on exclut ici — \b les protège.
    assert not hors_perimetre(
        "labecanerie", "Moteur", "Vilebrequin Nuova Mazzucchelli pour vélomoteur 48cc")
    assert not hors_perimetre(
        "labecanerie", "Partie cycle", "Restaurez et réparez votre VéloSolex")


def test_le_titre_n_ecarte_rien_chez_les_autres_marchands():
    assert not hors_perimetre("speedway", "Partie cycle", "Démonte pneu vélo Michelin")
