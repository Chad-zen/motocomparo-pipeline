"""Le rayon « Batteries & chargeurs » (31), ajoute le 18/10/2026 : 1 182 offres
de batteries etaient en « non classe » faute de rayon pour les recevoir."""

from mcpipe.category import classify

BATTERIE = 31
GANTS = 8
INTERCOM_ET_GPS = 19


def test_les_rayons_batterie_des_marchands_vont_au_rayon_batteries():
    for chemin in ("Electrique > Batterie > Batterie",
                   "Batteries & pièces electriques",
                   "batteries",
                   "Atelier & Stand > Chargeur de batterie > Chargeur de batterie",
                   "Atelier & Stand > Chargeur de batterie > Câble de batterie",
                   "Atelier & Stand > Chargeur de batterie > Testeur de batterie"):
        assert classify(chemin) == BATTERIE, chemin


def test_sans_rayon_le_titre_decide():
    assert classify(None, "BS Battery SLA YTX24HL sans entretien") == BATTERIE


def test_des_gants_chauffants_a_batterie_restent_des_gants():
    assert classify("Gants chauffants à batterie") == GANTS


def test_electronique_et_intercoms_ne_bougent_pas():
    assert classify("Intercom Bluetooth") == INTERCOM_ET_GPS
    assert classify("GPS moto") == INTERCOM_ET_GPS
