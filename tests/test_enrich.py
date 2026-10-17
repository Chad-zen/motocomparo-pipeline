"""Unit tests for `enrich`'s per-offer category decisions.

Pure and offline (no DB). They lock in the conservative rules: a coarse-bucket
offer is only reclassified on a confident, *different* read, and a helmet's
subtype is borrowed from a GTIN neighbour before the title is trusted — the
title being the signal that can name two types at once, or call the
adventure/trail family "enduro" where every other merchant says integral.
"""

from __future__ import annotations

import pytest

from mcpipe.enrich import (
    decide_helmet_category,
    decide_override,
    helmet_subtype_from_title,
    is_helmet_accessory,
)

CASUAL = 23  # apparel_casual — FC-Moto's `tops` maps here
JACKET = 6
PANTS = 7
UNKNOWN = 25

HELMET = 1  # generic parent — must never be written or borrowed
INTEGRAL = 2
JET = 3
MODULAR = 4
CROSS = 5


# --- rule 1: coarse apparel buckets, read from the title -------------------


def test_real_jacket_title_is_reclassified():
    assert decide_override("Alpinestars Dice Veste textile moto", CASUAL) == JACKET
    assert decide_override("Blouson en cuir Ixon", CASUAL) == JACKET


def test_trousers_title_is_reclassified():
    assert decide_override("Pantalon textile moto Revit", CASUAL) == PANTS


def test_title_without_strong_keyword_is_left_alone():
    assert decide_override("Klim Mesa Falls Wool Chemise à manches longues", CASUAL) is None


def test_no_override_when_title_matches_current_mapping():
    assert decide_override("Tee-shirt Alpinestars", CASUAL) is None


def test_empty_title_is_safe():
    assert decide_override(None, CASUAL) is None
    assert decide_override("", CASUAL) is None


# --- helmet subtype read from a title --------------------------------------


def test_title_names_one_subtype():
    assert helmet_subtype_from_title("Casque jet Shark Nano") == JET
    assert helmet_subtype_from_title("Shot Lite Core Casque de motocross") == CROSS
    assert helmet_subtype_from_title("Casque modulable Nolan N100") == MODULAR
    assert helmet_subtype_from_title("Casque intégral AGV K6") == INTEGRAL


def test_title_naming_two_subtypes_is_ambiguous():
    # the real trap: a modular helmet described by its integral chin bar
    assert helmet_subtype_from_title("Casque modulable à mentonnière intégrale") is None


def test_title_without_subtype_says_nothing():
    assert helmet_subtype_from_title("HJC i91 Casque") is None
    assert helmet_subtype_from_title(None) is None


# --- rule 2: the helmet cascade --------------------------------------------


def test_non_moto_helmet_goes_to_unknown():
    google = "Sporting Goods > Outdoor Recreation > Cycling > Bicycle Helmets"
    assert decide_helmet_category("Casque jet", [JET], google) == UNKNOWN


def test_unanimous_neighbours_are_borrowed():
    assert decide_helmet_category("HJC i91 Casque", [JET, JET], None) == JET


def test_borrowing_outranks_the_title():
    # FC-Moto titles the adventure family "enduro/cross"; neighbours say
    # integral. Trusting the title here would contradict merges that work.
    assert decide_helmet_category("Klim X1 Alpha Barre Enduro", [INTEGRAL], None) == INTEGRAL


def test_neighbours_disagreeing_means_abstain():
    assert decide_helmet_category("HJC i91 Casque", [JET, MODULAR], None) is None


def test_generic_and_unknown_neighbours_are_not_lendable():
    # a neighbour that only says "helmet" or "unknown" carries no subtype:
    # it must neither be borrowed nor counted as agreement
    assert decide_helmet_category("Casque jet Shark Nano", [HELMET, UNKNOWN], None) == JET


def test_title_is_the_fallback_when_nobody_can_lend():
    assert decide_helmet_category("Casque modulable Nolan N100", [], None) == MODULAR


def test_no_lender_and_no_title_signal_leaves_it_alone():
    assert decide_helmet_category("HJC i91 Casque", [], None) is None


# --- spare parts sold inside the helmet bucket -----------------------------


def test_a_visor_is_an_accessory_not_a_helmet():
    # the helmet type in these titles says which helmet the part FITS
    assert is_helmet_accessory("Shark RS Jet Visière") is True
    assert is_helmet_accessory("AGV GT3-1 Sportmodular Pinlock Visière") is True
    assert is_helmet_accessory("Acerbis Flip FS-606 visière") is True
    assert is_helmet_accessory("Bandit JET Visière du casque") is True
    assert is_helmet_accessory("Bandit Bubble Visor pour Jet Helmet") is True
    assert is_helmet_accessory("Coiffe de casque BELL Moto 3") is True


def test_a_helmet_whose_model_name_contains_visor_is_not_an_accessory():
    # the real trap: "N20-2 Visor" is a model name, the item IS a jet helmet
    assert is_helmet_accessory("Nolan N20-2 Visor Dolce Vita Casque à réaction") is False
    assert is_helmet_accessory("Nolan N21 Visor 06 Verniciatura Speciale Casque jet") is False
    # a helmet merely mentioning its own screen stays a helmet
    assert is_helmet_accessory("Casque intégral Shoei avec écran solaire") is False


def test_accessories_outrank_borrowing():
    # whatever a neighbour calls it, a visor is not a helmet
    # 17/10/2026 : une piece de casque va en categorie 30, pas en « non classe »
    # (25), pour qu'elle retrouve son rayon plutot que de disparaitre
    assert decide_helmet_category("Shark RS Jet Visière", [JET], None) == 30


def test_flip_is_not_a_modular_keyword():
    # "Flip" is a product line here, it used to turn 27 visors into modulars
    assert helmet_subtype_from_title("Acerbis Flip FS-606") is None


# --- les rayons ajoutés le 14/09/2026 ----------------------------------------

def test_les_maillots_cross_ont_enfin_un_rayon():
    """7 293 offres tombaient dans « non classé » faute de case."""
    from mcpipe.category import classify
    assert classify("Maillot Motocross") == 27
    assert classify("Équipement Cross > Maillot cross > Maillot de cross") == 27


def test_les_masques_ont_enfin_un_rayon():
    from mcpipe.category import classify
    assert classify("Masques") == 26
    assert classify("goggles") == 26


def test_une_casquette_est_un_vetement_casual():
    from mcpipe.category import classify
    assert classify("caps") == 23
    assert classify("Casquette") == 23


def test_les_frontieres_de_mot_protegent_des_faux_positifs():
    """`caps?` sans frontière attrapait « capot » et « capacité »."""
    from mcpipe.category import classify
    assert classify("capacite du reservoir") == 25
    assert classify("Capot moteur") == 15       # pris par la règle « moteur »


def test_aucune_regression_sur_les_rayons_existants():
    from mcpipe.category import classify
    assert classify("Casque cross") == 5
    assert classify("Casque jet") == 3
    assert classify("Blouson") == 6
    assert classify("Gants") == 8
    assert classify("Bottes") == 9


# --- le fourre-tout « Protections » -------------------------------------------
#
# Le rayon 11 mélangeait ce qui protège le pilote et ce qui protège la moto.
# Conséquence visible, signalée le 14/09/2026 : sur la fiche d'une protection
# cervicale, l'étagère « même gamme de prix » proposait un pare-carter.

@pytest.mark.parametrize("titre,attendu", [
    # la moto
    ("Pare-carter SW-MOTECH Crash bar - Noir Honda", 29),
    ("Protège réservoir Puig HONDA CMX REBEL", 29),
    ("Sabot moteur SW-MOTECH Aluminium - Noir", 29),
    ("Protection de silencieux R&G Racing gauche noir", 29),
    # le pilote
    ("ALPINESTARS Neck Brace BNS TECH-2", 28),
    ("Gilet de protection Acerbis KOERTA 2.0 noir/gris", 28),
    ("Dorsale RST niveau 1", 28),
    ("Macna Korus Veste protectrice", 28),
    # ni l'un ni l'autre : ces rayons existent déjà
    ("Bulle Puig Touring", 18),
    ("Garde boue Ufo avant vert", 18),
    ("Stickers de fourche Puig Kit Autocollants Bleu", 24),
])
def test_le_rayon_protections_est_decoupe(titre, attendu):
    from mcpipe.enrich import protection_subtype_from_title
    assert protection_subtype_from_title(titre) == attendu


def test_un_titre_sans_mot_cle_reste_ou_il_est():
    """Une offre laissée où elle est ne casse rien ; mal rangée, si.

    29 % des 44 350 offres du rayon ne sont décidées par aucune règle — petite
    visserie, kits de fixation. Elles restent dans « Protections ».
    """
    from mcpipe.enrich import protection_subtype_from_title
    assert protection_subtype_from_title("Kit Visserie pour Plastiques Bolt") == 24
    assert protection_subtype_from_title("Acerbis TC/S 2024") is None
    assert protection_subtype_from_title(None) is None


# --- l'emprunt de taille : qui doit être en vente, et qui n'a pas à l'être ----

def _bloc(nom: str) -> str:
    """Un morceau de la requête d'emprunt, découpé sur ses CTE."""
    from mcpipe.enrich import _BORROW_SIZE
    reperes = ["WITH parent_ean AS (", "donors AS (", "agreed AS (",
               "INSERT INTO offer_size_override"]
    i = reperes.index(nom)
    debut = _BORROW_SIZE.index(nom)
    fin = (_BORROW_SIZE.index(reperes[i + 1], debut)
           if i + 1 < len(reperes) else len(_BORROW_SIZE))
    return _BORROW_SIZE[debut:fin]


def _sans_commentaires(sql: str) -> str:
    import re
    return re.sub(r"--.*", "", sql)


def test_le_donneur_n_a_pas_besoin_d_etre_en_vente():
    """La taille qu'un code-barres désigne est une propriété PERMANENTE de
    l'article. Qu'un marchand le stocke encore ou non n'y change rien.

    Le 18/09/2026, un casque Airoh affichait cinq tailles Motoblouz empruntées
    et une sixième « non communiquée » : son donneur — le 2XL de FC-Moto, taille
    déclarée dans son flux — avait quitté la vente six jours plus tôt. Le trou
    apparaissait au milieu d'une série de tailles du MÊME marchand, ce qui
    ressemble à un défaut du site, et en était un. 384 offres sur 237 fiches."""
    assert "is_live" not in _sans_commentaires(_bloc("donors AS ("))


def test_le_receveur_lui_doit_etre_en_vente():
    """L'inverse n'est pas vrai : écrire une taille sur une offre retirée de la
    vente ne sert personne et encombrerait la table."""
    assert "o.is_live" in _sans_commentaires(_bloc("INSERT INTO offer_size_override"))


def test_la_garde_contre_le_code_barres_reutilise_ignore_la_vente():
    """Ce bloc détecte un marchand qui réutilise UN code-barres sur toute une
    série de tailles. Si une offre de la série n'est plus en vente, la
    réutilisation reste un fait : restreindre la garde aux offres vivantes
    l'affaiblirait au moment précis où elle sert."""
    assert "is_live" not in _sans_commentaires(_bloc("WITH parent_ean AS ("))


# 17/10/2026 : lunettes, casquettes, coussinets et pare-soleil dans les pages casque
# integral et casque cross. Le titre d'une piece FC-Moto finit par son type.
def test_les_pieces_sans_mot_visiere_sont_des_accessoires():
    for titre in ("MOMO Hornet Coussinets de joue", "GIVI 10.8 / HX05 Pare-soleil",
                  "Scott 550 Series Ensemble de vis", "Suomy 3Logy Couvrir",
                  "Bogotto V587 / Casque universel Peak", "Redbike Hip Casque Peak",
                  "FOX V2 Voke Helmet Peak", "Oneal Volt V1 Pic casque",
                  "Scorpion Lunettes Lentilles", "Nolan N70-2 X Rideau de menton",
                  "Alpinestars Supertech R7 Déflecteur de souffle",
                  "Oxford Message Pare-chocs casque", "Nolan N80-8 Clima Comfort Doublure intérieure",
                  "Sac à casque Alpinestars S-M8 SOFT", "Bonnet sous casque Shot FILET"):
        assert is_helmet_accessory(titre) is True, titre


def test_un_vrai_casque_n_est_pas_pris_pour_une_piece():
    # « Peak » est une version (720 EUR) ; « avec lunettes » / « avec masque » un lot
    # vendu avec le casque ; « Seventy4 » contient « event » ; un casque s'ecrit
    # en commencant par « Casque ».
    for titre in ("Casque intégral Arai Quantic Peak rouge- S", "Casque cross Arai MX-V Evo Peak jaune- XS",
                  "Leatt ADV 8.5 Casque avec lunettes", "Casque cross Leatt 8.5 avec masque 5.5 2025",
                  "Fox Racing V3 Seventy4 white- L", "FOX V3 Seventy4 MIPS Casque de motocross",
                  "Casque jet LS2 Airflow avec pare-soleil intégré", "Shoei NXR2 Casque intégral"):
        assert is_helmet_accessory(titre) is False, titre


def test_deuxieme_tour_de_mots_de_pieces():
    for titre in ("Bell 3Snap 510 Flat Bouclier", "Caberg Ghost Masque", "Scorpion Covert-X Masque",
                  "Peroz Sommet casque à réaction / Sommet universel casque",
                  "Leatt DBX/GPR Pro/Pro Lite Bolt Kit", "Acerbis Airstrike Kit d’accessoires",
                  "Oneal Airflaps EX-SRS Système de ventilation", "Bell Broozer Menton",
                  "Icon Airform Speedfin de remplacement", "Scorpion DKS541 Objectif à épingle XLT",
                  "Oxford Ultra Clear Pro Feuille anti-brouillard", "Sena Impulse Protège-nez et menton",
                  "Alpinestars Yamaha S-M3 Casque Enfant Peak", "Bell MX-10 MIPS Protections pour les joues jeunesse"):
        assert is_helmet_accessory(titre) is True, titre
    # des casques, eux, restent des casques
    for titre in ("Casque cross Leatt 8.5 avec masque 5.5 2025", "Oneal 7Series Strain Casque",
                  "Oneal 5Series Rider Casque", "Casque intégral Arai Quantic Peak rouge- S",
                  "Casque modulable Shark Evo-One 2 à mentonnière relevable"):
        assert is_helmet_accessory(titre) is False, titre
