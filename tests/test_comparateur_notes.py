"""La note du comparateur ne doit rien devoir a ce que tout le monde a (24/10/2026).

Les notes etaient peu fiables : un jet d'entree de gamme sans aucun essai recevait 9,5 de protection, bati sur une
calotte « fibre » (9 sur 10, alors que la matiere dit le poids et le prix) et sur l'homologation 22.06 (10 sur 10 pour
tout casque en vente, la 22.05 etant interdite a la vente).
"""

from mcsite import queries


def c(nom, valeur, source="flux"):
    return {"nom": nom, "valeur": valeur, "source": source}


def test_un_casque_sans_essai_sharp_n_a_pas_d_indice_de_protection():
    carac = [c("calotte", "fibre"), c("homologation", "22.06"), c("poids_g", "1350"), c("nombre_coques", "3")]
    assert queries.indice_protection(carac, "helmet.jet") is None


def test_un_casque_sans_essai_n_a_pas_de_note_d_ensemble_meme_bien_equipe():
    carac = [c("ventilation", "True"), c("pinlock", "fourni"), c("ecran_solaire", "True"),
             c("interieur_amovible", "True"), c("calotte", "fibre"), c("homologation", "22.06")]
    assert queries.note_globale(carac, "helmet.integral") is None


def test_un_casque_avec_sharp_est_note_et_l_homologation_22_06_n_ajoute_rien():
    base = [c("note_securite", "4", "sharp"), c("poids_g", "1500", "sharp")]
    sans = queries.indice_protection(base, "helmet.integral")
    avec = queries.indice_protection(base + [c("homologation", "22.06")], "helmet.integral")
    assert sans and avec and sans["note"] == avec["note"]
    assert all(libelle != "Homologation" for libelle, _ in avec["detail"])
    assert avec["independante"] is True


def test_un_vieux_casque_22_05_est_note_en_retrait():
    base = [c("note_securite", "4", "sharp"), c("poids_g", "1500", "sharp")]
    neuf = queries.indice_protection(base + [c("homologation", "22.06")], "helmet.integral")
    ancien = queries.indice_protection(base + [c("homologation", "22.05")], "helmet.integral")
    assert ancien["note"] < neuf["note"]


def test_la_calotte_n_entre_plus_dans_la_protection():
    base = [c("note_securite", "4", "sharp"), c("poids_g", "1500", "sharp")]
    a = queries.indice_protection(base + [c("calotte", "carbone")], "helmet.integral")
    b = queries.indice_protection(base + [c("calotte", "thermoplastique")], "helmet.integral")
    assert a["note"] == b["note"]


def test_calotte_contradictoire_entre_deux_sources_non_verifiees():
    flux_attribut = [c("calotte", "carbone", "flux"), c("calotte", "thermoplastique", "attribut")]
    assert queries.calotte_contradictoire(flux_attribut) is True
    # une valeur verifiee du modele tranche
    assert queries.calotte_contradictoire(flux_attribut + [c("calotte", "thermoplastique", "manuel")]) is False
    # polycarbonate et thermoplastique sont la meme famille
    assert queries.calotte_contradictoire([c("calotte", "polycarbonate"), c("calotte", "thermoplastique", "attribut")]) is False
    assert queries.calotte_contradictoire([c("calotte", "carbone")]) is False
