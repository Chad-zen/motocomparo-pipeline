"""Un meme casque, deux fiches par tailles (23/10/2026) : la cle de comparaison est pure."""

from mcpipe.tailles_coupees import titre_sans_taille


def test_la_taille_finale_est_retiree():
    assert titre_sans_taille("Casque jet Shoei J-Cruise 3 blue metallic mat- XS") == \
        titre_sans_taille("Casque jet Shoei J-Cruise 3 blue metallic mat- M")


def test_deux_couleurs_restent_deux_titres():
    assert titre_sans_taille("Casque X noir mat - M") != titre_sans_taille("Casque X blanc - M")


def test_un_s_dans_le_nom_n_est_pas_une_taille():
    # le « s » de « Aviator 3s » ne doit pas disparaitre (pas de separateur avant)
    assert titre_sans_taille("Casque Aviator 3s") == "casque aviator 3s"
