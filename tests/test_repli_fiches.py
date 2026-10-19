"""La regle qui reunit les fiches d'un meme casque coupees par un mot sans sens (repli_fiches.py)."""

from mcpipe.repli_fiches import FicheRepli, paire_possible, trouver_paires

ALIAS: dict[str, str] = {}
FIN = frozenset({"finition"})


def fiche(i, jetons, *, marque="shoei", rayon=4, couleur="WH", genre="U-A", annee=None,
          nb=5, prix=550.0, cb=None, fiables=True):
    jetons = frozenset(jetons.split())
    cb = cb if cb is not None else {"4512048807573": jetons}
    return FicheRepli(i, marque, rayon, couleur, genre, annee, jetons, nb, prix, cb, fiables)


def neotec():
    courte = fiche(249121, "3 neotec", cb={"A": frozenset("3 neotec finition".split()),
                                           "B": frozenset("3 neotec finition".split())})
    longue = fiche(174603, "3 neotec finition", nb=2, prix=609.0,
                   cb={"C": frozenset("3 neotec finition".split())})
    return courte, longue


def test_le_cas_shoei_neotec_est_reuni():
    c, l = neotec()
    assert paire_possible(c, l, ALIAS)
    assert trouver_paires([c, l], ALIAS) == [(c, l)]


def test_un_mot_hors_liste_blanche_n_est_jamais_ignore():
    c = fiche(1, "gt-air 3", cb={"A": frozenset("gt-air 3 air".split())})
    l = fiche(2, "gt-air 3 air")
    assert not paire_possible(c, l, ALIAS)
    assert not paire_possible(c, l, ALIAS, mots=frozenset({"decor"}))


def test_mat_et_brillant_restent_deux_produits():
    c, l = neotec()
    mat = fiche(174603, "3 neotec finition", couleur="WH|MAT", nb=2, prix=609.0, cb=l.codes_barres)
    assert not paire_possible(c, mat, ALIAS)


def test_une_couleur_inconnue_ne_prouve_rien():
    c = fiche(1, "3 neotec", couleur="unknown", cb={"A": frozenset("3 neotec finition".split())})
    l = fiche(2, "3 neotec finition", couleur="unknown")
    assert not paire_possible(c, l, ALIAS)


def test_une_annee_presente_d_un_seul_cote_refuse():
    c, l = neotec()
    assert not paire_possible(c, fiche(174603, "3 neotec finition", annee=2024, nb=2, prix=609.0), ALIAS)


def test_un_code_barres_sans_le_mot_ne_bloque_pas_si_un_autre_l_a_ecrit():
    c = fiche(1, "3 neotec", cb={"A": frozenset("3 neotec finition".split()), "B": frozenset("3 neotec".split())})
    assert paire_possible(c, fiche(2, "3 neotec finition"), ALIAS)


def test_si_aucun_code_barres_n_a_ecrit_le_mot_rien_ne_prouve_la_paire():
    c = fiche(1, "3 neotec", cb={"A": frozenset("3 neotec".split()), "B": frozenset("3 neotec".split())})
    assert not paire_possible(c, fiche(2, "3 neotec finition"), ALIAS)


def test_une_offre_non_fiable_ou_sans_code_barres_bloque():
    c, l = neotec()
    assert not paire_possible(fiche(249121, "3 neotec", cb=c.codes_barres, fiables=False), l, ALIAS)
    assert not paire_possible(fiche(249121, "3 neotec", cb={}), l, ALIAS)


def test_deux_prix_medians_trop_eloignes_ne_sont_pas_le_meme_casque():
    c, l = neotec()
    assert not paire_possible(c, fiche(174603, "3 neotec finition", prix=900.0), ALIAS)


def test_la_marque_et_le_rayon_sont_durs():
    c, l = neotec()
    assert not paire_possible(c, fiche(174603, "3 neotec finition", marque="arai"), ALIAS)
    assert not paire_possible(c, fiche(174603, "3 neotec finition", rayon=2), ALIAS)


def test_une_fiche_courte_a_deux_longues_n_est_dans_aucune_paire():
    c, l = neotec()
    l2 = fiche(3, "3 neotec finition", annee=None, nb=1, prix=600.0)
    # deux longues de memes jetons : c est ambigu, on ne choisit pas
    assert trouver_paires([c, l, l2], ALIAS) == []


def test_une_chaine_n_est_pas_une_paire():
    a = fiche(1, "x", cb={"A": frozenset("x finition".split())})
    b = fiche(2, "x finition", cb={"B": frozenset("x finition".split())})
    c = fiche(3, "x finition", annee=None)
    assert trouver_paires([a, b, c], ALIAS) == []
