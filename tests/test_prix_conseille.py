"""Le prix public conseille : un PVC n'est publie que s'il est source (23/10/2026)."""

from mcpipe.prix_conseille import choisir_pvc


def test_deux_marchands_d_accord_donnent_le_pvc():
    assert choisir_pvc({"motoblouz": 209.99, "speedway": 209.99}, 157.40) == (209.99, 1, "motoblouz+speedway")


def test_l_accord_se_fait_a_un_pour_cent_pres_et_prend_la_valeur_haute():
    pvc, palier, _ = choisir_pvc({"motoblouz": 189.99, "speedway": 190.50}, 140)
    assert (pvc, palier) == (190.5, 1)


def test_la_becanerie_seule_ne_decide_jamais():
    assert choisir_pvc({"labecanerie": 143.95}, 120) is None


def test_la_becanerie_confirme_un_autre_marchand():
    assert choisir_pvc({"labecanerie": 159.95, "motoblouz": 159.95}, 135) == (159.95, 1, "labecanerie+motoblouz")


def test_motoblouz_seul_n_est_pas_publie():
    assert choisir_pvc({"motoblouz": 159.95}, 120) is None


def test_speedway_seul_est_publie_dans_la_fourchette():
    assert choisir_pvc({"speedway": 189.95}, 145.27) == (189.95, 2, "speedway")


def test_speedway_seul_hors_fourchette_est_ecarte():
    assert choisir_pvc({"speedway": 189.95}, 100) is None      # 1,9 x : tarif probablement perime
    assert choisir_pvc({"speedway": 150.00}, 149) is None      # sous 1,03 x : pas une remise


def test_desaccord_sans_paire_n_a_pas_de_pvc():
    # La Becanerie plus bas que Motoblouz et Speedway qui divergent aussi : on ne devine pas
    assert choisir_pvc({"labecanerie": 124.95, "motoblouz": 129.95, "speedway": 139.95}, 100) is None


def test_un_pvc_de_palier_1_au_dela_de_trois_fois_le_prix_est_ecarte():
    assert choisir_pvc({"motoblouz": 300, "speedway": 300}, 90) is None
