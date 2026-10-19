"""Le cas Macna Fluent (19/10/2026) : le meme blouson sur deux fiches parce que
FC-Moto ecrit « veste textile » et Speedway « blouson »."""

from mcpipe.consolider import Fiche, cle_nom, compatibles


def test_deux_ecritures_du_meme_nom_donnent_la_meme_cle():
    assert cle_nom("Blouson Fluent Veste") == cle_nom("Fluent Textile Veste") == frozenset({"fluent"})


def test_le_cuir_ne_se_confond_pas_avec_le_textile():
    assert cle_nom("Fluent Cuir Veste") != cle_nom("Fluent Textile Veste")


def test_deux_modeles_differents_gardent_deux_cles():
    assert cle_nom("Blouson Fluent Veste") != cle_nom("Blouson Rapid Veste")


def test_un_nom_fait_que_de_mots_de_type_ne_dit_rien():
    assert cle_nom("Blouson Veste") == frozenset()


def test_les_gardes_fous_du_match_s_appliquent_toujours():
    a = Fiche(1, "macna", 6, "H-A", None, "BK")
    assert compatibles(a, Fiche(2, "macna", 6, "H-A", None, "BK"), {})
    assert not compatibles(a, Fiche(3, "macna", 6, "H-A", None, "RD"), {})   # couleur
    assert not compatibles(a, Fiche(4, "macna", 6, "F-A", None, "BK"), {})   # genre
    assert not compatibles(a, Fiche(5, "dainese", 6, "H-A", None, "BK"), {})  # marque
