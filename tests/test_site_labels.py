"""How the site names a size.

`equivalences_tailles` is the one display rule that can hide offers when it is
wrong — it decides which filter button a row answers to — so each case here is
a real page: the Helstons Swallow gloves (four merchants, three vocabularies)
and the parent-barcode shape that would collapse three sizes into one button.
"""

from __future__ import annotations

import pytest

from mcsite import labels


def _o(marchand, taille, gtin=None):
    return {"merchant": marchand, "size_code": taille, "gtin": gtin}


def test_tailles_du_meme_code_barre_fusionnent():
    """Helstons Swallow: four merchants, four barcodes, three vocabularies."""
    rows = [
        _o("fcmoto", "6", "3662136073524"),
        _o("speedway", "XS", "3662136073524"),
        _o("fcmoto", "7", "3662136073531"),
        _o("speedway", "S", "3662136073531"),
    ]
    f = labels.equivalences_tailles(rows)
    assert f["6"] == f["XS"] == "XS / 6"   # Speedway passe avant FC-Moto
    assert f["7"] == f["S"] == "S / 7"


def test_taille_seule_reste_elle_meme():
    f = labels.equivalences_tailles([_o("fcmoto", "M", "111"), _o("fcmoto", "L", "222")])
    assert f == {"M": "M", "L": "L"}


def test_code_barre_parent_ne_fusionne_rien():
    """One merchant listing S, M and L under one barcode is using a code that
    covers a range: it proves nothing, and fusing them would leave one button
    for three sizes."""
    rows = [_o("fcmoto", t, "999") for t in ("S", "M", "L")]
    rows.append(_o("speedway", "M", "999"))
    f = labels.equivalences_tailles(rows)
    assert f == {"S": "S", "M": "M", "L": "L"}


def test_au_plus_deux_libelles():
    rows = [
        _o("motoblouz", "M", "1"), _o("speedway", "8", "1"),
        _o("labecanerie", "L", "1"), _o("fcmoto", "42", "1"),
    ]
    f = labels.equivalences_tailles(rows)
    assert f["M"] == "M / 8"
    assert set(f.values()) == {"M / 8"}


# --- une taille en fin de titre ------------------------------------------------
#
# « Housse moto Ixon BLANKY - M » sur une fiche qui compare M, L, XL et 2XL :
# le titre ment avant même que le visiteur lise le tableau. Signalé par la
# propriétaire le 14/09/2026.
#
# La règle est ÉTROITE à dessein. L'affichage du projet montre le titre du
# marchand tel quel (décision du 13/09) : une version qui retirait la marque, la
# couleur et le nom de rayon en abîmait d'autres — « Cuir Swallow T7 ».

@pytest.mark.parametrize("titre,attendu", [
    ("Housse moto Ixon BLANKY - M", "Housse moto Ixon BLANKY"),
    ("Housse Moto Ixon Blanky (Taille M)", "Housse Moto Ixon Blanky"),
    ("Housse moto Ixon BLANKY - 2XL", "Housse moto Ixon BLANKY"),
    ("Protection cervicale Alpinestars - XS", "Protection cervicale Alpinestars"),
])
def test_une_taille_terminale_est_retiree(titre, attendu):
    from mcsite.labels import sans_taille_finale
    assert sans_taille_finale(titre) == attendu


@pytest.mark.parametrize("titre", [
    "Rev It Cuir Swallow T7",            # pas de séparateur : on ne touche pas
    "Casque Shark Skwal - Noir Mat",     # ce n'est pas une taille
    "Blouson Ixon Pulsion Air",
    "Casque LS2 FF811 - Vector II",
])
def test_le_reste_du_titre_est_intact(titre):
    from mcsite.labels import sans_taille_finale
    assert sans_taille_finale(titre) == titre


def test_un_titre_reduit_a_rien_est_garde():
    """Un titre vide est pire qu'un titre qui annonce une taille."""
    from mcsite.labels import sans_taille_finale
    assert sans_taille_finale("XL") == "XL"


# --- la queue « nom de rayon + marque » ---------------------------------------
#
# Certains marchands collent leur arborescence en fin de titre :
#     « Casque Cross Alpinestars SM3 Falcon Rouge - Casque Cross ALPINESTARS »
#
# La condition de coupe est la RÉPÉTITION DE LA MARQUE, et c'est elle qui rend
# la règle sûre. Couper à tous les tirets perdrait « - SOLID », qui est un
# coloris — l'erreur qui avait fait rejeter le reconstructeur de noms le 13/09.
#
# Mesuré le 14/09/2026 : 1 538 titres concernés sur 28 716 fiches comparables,
# 24 coupes relues une par une, 24 queues de rayon, aucune perte.

@pytest.mark.parametrize("titre,marque,attendu", [
    ("Casque Cross Alpinestars SM3 Falcon Rouge - Casque Cross ALPINESTARS",
     "alpinestars", "Casque Cross Alpinestars SM3 Falcon Rouge"),
    ("Bottes TCX Infinity 3 Gore-Tex Noir - Bottes et chaussures TCX",
     "tcx", "Bottes TCX Infinity 3 Gore-Tex Noir"),
    # « SW-Motech », « sw motech » et « swmotech » doivent se reconnaître
    ("Sacoche SW-Motech LC1 Droit - Bagagerie moto souple SW-Motech",
     "swmotech", "Sacoche SW-Motech LC1 Droit"),
])
def test_la_queue_qui_repete_la_marque_est_retiree(titre, marque, attendu):
    from mcsite.labels import sans_queue_de_rayon
    assert sans_queue_de_rayon(titre, marque) == attendu


@pytest.mark.parametrize("titre,marque", [
    # SOLID est un coloris, pas un rayon : la marque n'y figure pas.
    ("Casque Scorpion Exo EXO-RACE AIR - SOLID", "scorpion"),
    ("Gants Macna THANDOR", "macna"),
    ("Pantalon Ixon Eddas - L30", "ixon"),
])
def test_une_queue_qui_dit_quelque_chose_est_gardee(titre, marque):
    from mcsite.labels import sans_queue_de_rayon
    assert sans_queue_de_rayon(titre, marque) == titre


def test_on_ne_coupe_pas_jusqu_a_rien():
    from mcsite.labels import sans_queue_de_rayon
    assert sans_queue_de_rayon("Ixon - Blouson IXON", "ixon") == "Ixon - Blouson IXON"


# --- le palier de couleur d'une remise --------------------------------------
#
# Les bornes sont une promesse faite au visiteur : une affaire annoncée en rouge
# doit en être une. Elles sont écrites une seule fois (`labels.SEUILS_REMISE`),
# relues par le gabarit et par le script de la fiche — ces tests fixent le
# comportement aux bornes exactes, là où une inégalité mal choisie se cache.



def test_sous_vingt_pour_cent_reste_sobre():
    assert labels.niveau_remise(0) == "sobre"
    assert labels.niveau_remise(19) == "sobre"
    assert labels.niveau_remise(19.9) == "sobre"


def test_vingt_pour_cent_passe_en_orange():
    """20 % est DANS la tranche orange : « entre 20 et 35 », borne incluse."""
    assert labels.niveau_remise(20) == "orange"
    assert labels.niveau_remise(35) == "orange"


def test_au_dela_de_trente_cinq_c_est_rouge():
    """« Plus de 35 » : 35 lui-même reste orange, 36 bascule."""
    assert labels.niveau_remise(35.1) == "rouge"
    assert labels.niveau_remise(36) == "rouge"
    assert labels.niveau_remise(100) == "rouge"


def test_sans_remise_aucun_palier():
    assert labels.niveau_remise(None) == ""


def test_les_bornes_restent_celles_annoncees():
    """Si quelqu'un déplace les seuils, le gabarit et le script suivront —
    mais la demande, elle, disait 20 et 35."""
    assert labels.SEUILS_REMISE == (20, 35)
