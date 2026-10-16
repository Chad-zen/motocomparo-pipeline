"""Regrouper les fiches qui se dédoublent pour un même code-barres (16/10/2026).

Les garde-fous sont purs : testés sans base. La fausse fusion est le risque que
ce projet refuse le plus, donc chaque garde-fou a son test.
"""

from __future__ import annotations

from mcpipe import consolider as c
from mcpipe.consolider import Fiche


def f(i, marque="shark", rayon=2, genre="H-A", annee=None, couleur="BK|MAT", n=1):
    return Fiche(i, marque, rayon, genre, annee, couleur, n)


def test_meme_casque_deux_fiches_est_regroupable():
    # Shark i3 : « noir mat, homme » chez trois marchands, « noir, non précisé » chez un
    assert c.compatibles(f(1), f(2, genre="U-A", couleur="BK"), {})


def test_deux_marques_differentes_ne_se_regroupent_jamais():
    assert not c.compatibles(f(1, marque="shark"), f(2, marque="hjc"), {})


def test_un_alias_valide_rend_deux_ecritures_de_marque_identiques():
    alias = {"rg": "rgracing"}
    assert c.compatibles(f(1, marque="rg"), f(2, marque="rgracing"), alias)
    assert not c.compatibles(f(1, marque="rg"), f(2, marque="rgracing"), {})


def test_rayon_age_sexe_annee_couleur_sont_des_garde_fous_durs():
    assert not c.compatibles(f(1, rayon=2), f(2, rayon=3), {})              # rayon
    assert not c.compatibles(f(1, genre="H-A"), f(2, genre="H-E"), {})      # adulte / enfant
    assert not c.compatibles(f(1, genre="H-A"), f(2, genre="F-A"), {})      # homme / femme
    assert not c.compatibles(f(1, annee=2024), f(2, annee=2025), {})        # année
    assert not c.compatibles(f(1, couleur="BK"), f(2, couleur="RD"), {})    # couleur


def test_une_couleur_inconnue_ou_une_annee_absente_ne_bloque_pas():
    assert c.compatibles(f(1, couleur="unknown"), f(2, couleur="RD"), {})
    assert c.compatibles(f(1, annee=None), f(2, annee=2025), {})


def test_un_code_barres_ne_relie_que_si_toutes_les_fiches_sont_compatibles():
    assert c.gtin_sur([f(1), f(2), f(3)], 100.0, 120.0, {})
    assert not c.gtin_sur([f(1), f(2), f(3, marque="hjc")], 100.0, 120.0, {})
    assert not c.gtin_sur([f(1)], 100.0, 100.0, {})


def test_un_rapport_de_prix_superieur_a_cinq_n_est_pas_le_meme_article():
    assert not c.gtin_sur([f(1), f(2)], 10.0, 60.0, {})
    assert c.gtin_sur([f(1), f(2)], 10.0, 50.0, {})


def test_la_fermeture_transitive_forme_des_groupes():
    g = c.former_groupes([[1, 2], [2, 3], [10, 11]])
    assert sorted(sorted(x) for x in g) == [[1, 2, 3], [10, 11]]


def test_le_survivant_est_la_fiche_aux_plus_d_offres_puis_la_plus_ancienne():
    assert c.choisir_survivant([f(5, n=3), f(2, n=9), f(7, n=9)]) == 2


def test_la_cle_d_un_groupe_ne_depend_pas_de_l_ordre():
    assert c.cle_groupe([3, 1, 2]) == c.cle_groupe({1, 2, 3})
    assert c.cle_groupe([1, 2]) != c.cle_groupe([1, 2, 3])
